# tui_components/messages/stream_handler.py
"""
MessageStreamHandler - 参考 demo_tui_stream_output.py 的简洁实现
处理 AI 消息流和工具调用
"""
import asyncio
import time
import json
import sys
import os
from typing import Callable, Optional, Dict, Set
from datetime import datetime
from langchain_core.messages import AIMessage, ToolMessage as LC_ToolMessage

from .types import BotMessage, ToolMessage, ToolStatus
from .bot_widget import BotMessageWidget

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".qoze", "stream_debug.log")


def _log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] [STREAM] {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"[LOG ERROR] {e}", file=sys.stderr)


class MessageStreamHandler:
    """流式消息处理器"""

    UPDATE_INTERVAL = 0.15

    def __init__(self,
                 on_bot_created: Callable,
                 on_bot_updated: Callable,
                 on_tool_started: Optional[Callable[[str, str], None]] = None,
                 on_tool_completed: Optional[Callable[[str, str, bool], None]] = None,
                 on_stream_complete: Optional[Callable[[int], None]] = None):

        self.on_bot_created = on_bot_created
        self.on_bot_updated = on_bot_updated
        self.on_tool_started = on_tool_started
        self.on_tool_completed = on_tool_completed
        self.on_stream_complete = on_stream_complete

        self.current_bot_message = None
        self._active_tools: Dict[str, dict] = {}
        self._processed_tool_ids: Set[str] = set()
        self._last_update_time = 0
        self._accumulated_content = ""
        self._expecting_new_message = False
        self._accumulated_ai_message = None
        self._pending_update = False

    def reset(self):
        """重置状态"""
        self.current_bot_message = None
        self._active_tools.clear()
        self._processed_tool_ids.clear()
        self._last_update_time = 0
        self._accumulated_content = ""
        self._expecting_new_message = False
        self._accumulated_ai_message = None
        self._pending_update = False

    async def process_stream(self, stream):
        """处理流式输出"""
        _log("=" * 60)
        _log("Stream started")
        self.reset()
        chunk_count = 0

        try:
            async for message_chunk, metadata in stream:
                chunk_count += 1
                chunk_type = type(message_chunk).__name__

                try:
                    if isinstance(message_chunk, (AIMessage,)) or chunk_type in ["AIMessageChunk", "AIMessage"]:
                        await self._process_ai_message_chunk(message_chunk, chunk_count)
                    elif isinstance(message_chunk, (LC_ToolMessage,)) or chunk_type in ["ToolMessageChunk", "ToolMessage"]:
                        await self._process_tool_result(message_chunk, chunk_count)
                    
                    # 关键：让出事件循环，给 UI 刷新机会
                    await asyncio.sleep(0)
                except Exception as e:
                    _log(f"ERROR chunk {chunk_count}: {e}")
                    import traceback
                    _log(traceback.format_exc())
        except Exception as e:
            _log(f"Fatal error: {e}")
            import traceback
            _log(traceback.format_exc())
            raise

        if self._pending_update and self.current_bot_message:
            await self._flush_update()

        # 流式结束，切换到 Markdown 渲染
        if self.current_bot_message:
            self.current_bot_message.finalize()
            await asyncio.sleep(0)

        if self.on_stream_complete:
            estimated_tokens = int(len(self._accumulated_content) * 0.3)
            self.on_stream_complete(estimated_tokens)

        _log(f"Stream ended, chunks={chunk_count}")
        _log("=" * 60)

    async def _process_ai_message_chunk(self, message_chunk, chunk_count: int):
        """处理 AI 消息块 - 累积内容并检测 tool_calls"""
        thinking = self._extract_thinking(message_chunk)
        content = self._extract_content(message_chunk)

        if self._accumulated_ai_message is None:
            self._accumulated_ai_message = message_chunk
        else:
            self._accumulated_ai_message += message_chunk

        await self._handle_ai_content(message_chunk, thinking, content)

        if self._accumulated_ai_message.tool_calls:
            self._update_tool_calls_from_accumulated()

    def _update_tool_calls_from_accumulated(self):
        """从累积的 AI 消息中更新 tool_calls 信息，并立即显示新的 tool_calls"""
        for tool_call in self._accumulated_ai_message.tool_calls:
            tool_call_id = tool_call.get("id", "")
            if not tool_call_id:
                continue

            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("args", {}) or {}

            if tool_call_id in self._active_tools:
                # 更新现有 tool_call 的信息
                existing = self._active_tools[tool_call_id]
                updated = False
                
                # 更新 name
                if tool_name and not existing.get("name"):
                    existing["name"] = tool_name
                    updated = True
                
                # 更新 args（如果新的 args 有实质内容）
                existing_args = existing.get("args", {}) or {}
                if tool_args and len(tool_args) >= len(existing_args):
                    # 检查是否有实质内容
                    has_content = any(v for v in tool_args.values() if v)
                    if has_content or not any(v for v in existing_args.values() if v):
                        existing["args"] = tool_args
                        updated = True
                
                if updated:
                    # _log(f"Updated tool_call {tool_call_id}: name={tool_name}, args={tool_args}")
                    
                    # 检查是否需要显示（如果之前未显示过）
                    if tool_call_id not in self._processed_tool_ids:
                        has_content = any(v for v in (existing.get("args") or {}).values() if v)
                        if has_content:
                            # 现在有内容了，显示它
                            display_name = self._format_tool_display_name(
                                existing.get("name", ""), 
                                existing.get("args", {})
                            )
                            existing["display_name"] = display_name
                            
                            if self.on_tool_started:
                                self.on_tool_started(tool_call_id, display_name)
                                # _log(f"Displayed tool_call after update: {display_name}")
                            
                            self._processed_tool_ids.add(tool_call_id)
                    else:
                        # 已经显示过，检查是否需要更新显示名称
                        new_display = self._format_tool_display_name(
                            existing.get("name", ""), 
                            existing.get("args", {})
                        )
                        old_display = existing.get("display_name", "")
                        if new_display != old_display:
                            existing["display_name"] = new_display
                            # _log(f"Updated display_name: {old_display} -> {new_display}")
            else:
                # 新 tool_call，注册
                self._active_tools[tool_call_id] = {
                    "name": tool_name,
                    "args": tool_args,
                    "display_name": ""
                }
                _log(f"Registered new tool_call {tool_call_id}: name={tool_name}, args={tool_args}")
                
                # 检查 args 是否有实质内容
                has_content = any(v for v in (tool_args or {}).values() if v)
                
                if has_content:
                    # 有内容，立即显示
                    display_name = self._format_tool_display_name(tool_name, tool_args)
                    self._active_tools[tool_call_id]["display_name"] = display_name
                    
                    if self.on_tool_started:
                        self.on_tool_started(tool_call_id, display_name)
                        _log(f"Displayed tool_call immediately: {display_name}")
                    
                    self._processed_tool_ids.add(tool_call_id)
                else:
                    # 无内容，先不显示，等待后续更新
                    _log(f"Tool_call {tool_call_id} has no content yet, waiting for update")

    async def _process_tool_result(self, message_chunk, chunk_count: int):
        """处理工具执行结果 - 此时显示 tool_call 并通知完成"""
        tc_id = getattr(message_chunk, 'tool_call_id', 'unknown')
        _log(f"Tool result received for {tc_id}")

        await self._display_pending_tool_calls()

        tool_info = self._active_tools.pop(tc_id, None)

        if not tool_info and self._active_tools:
            _id, _info = list(self._active_tools.items())[-1]
            tool_info = _info
            self._active_tools.pop(_id)
            _log(f"Using last active tool: {_id}")

        if not tool_info:
            tool_info = {"name": "Tool", "display_name": "run: unknown"}
            _log("No tool_info found, using default")

        is_error = self._is_error(message_chunk)
        display_name = tool_info.get("display_name", "run: unknown")
        _log(f"Tool completed: display_name='{display_name}', is_error={is_error}")

        if self.on_tool_completed:
            self.on_tool_completed(tc_id, display_name, is_error)

        self._expecting_new_message = True
        self._accumulated_ai_message = None

    async def _display_pending_tool_calls(self):
        """显示待处理的 tool_calls（更新显示名称如果有变化）"""
        for tool_id, tool_info in list(self._active_tools.items()):
            tool_name = tool_info.get("name", "")
            tool_args = tool_info.get("args", {})
            
            # 重新计算 display_name（可能 args 在后续 chunk 中更新了）
            new_display_name = self._format_tool_display_name(tool_name, tool_args)
            old_display_name = tool_info.get("display_name", "")
            
            # 如果显示名称有变化，更新存储
            if new_display_name != old_display_name:
                tool_info["display_name"] = new_display_name
                # _log(f"Updated display_name for {tool_id}: {new_display_name}")

    @staticmethod
    def _format_tool_display_name(tool_name: str, tool_args: dict) -> str:
        """格式化工具显示名称"""
        if tool_name == "execute_command":
            cmd = tool_args.get("command", "")
            if cmd:
                short_cmd = cmd[:120] + ("..." if len(cmd) > 120 else "")
                return f"command: {short_cmd}"
            return "command: (empty)"
        elif tool_name == "read_file":
            path = tool_args.get("path", "")
            return f"read_file: {path}" if path else "read_file: (empty)"
        elif tool_name == "cat_file":
            paths = tool_args.get("paths", [])
            if isinstance(paths, str):
                paths_str = paths
            elif isinstance(paths, list):
                paths_str = ", ".join([str(p) for p in paths])
            else:
                paths_str = str(paths)
            if paths_str:
                short_paths = paths_str[:60] + ("..." if len(paths_str) > 60 else "")
                return f"cat_file: {short_paths}"
            return "cat_file: (empty)"
        elif tool_name == "tavily_search":
            query = tool_args.get("query", "")
            if query:
                short_q = query[:60] + ("..." if len(query) > 60 else "")
                return f"search: '{short_q}'"
            return "search: (empty)"
        elif tool_name == "browser_navigate":
            url = tool_args.get("url", "")
            return f"navigate: {url[:50]}" if url else "navigate: (empty)"
        elif tool_name == "browser_click":
            selector = tool_args.get("selector", "")
            return f"click: {selector[:50]}" if selector else "click: (empty)"
        elif tool_name == "browser_type":
            text = tool_args.get("text", "")
            return f"type: {text[:30]}" if text else "type: (empty)"
        elif tool_name == "browser_read_page":
            return "read page"
        elif tool_name == "browser_get_html":
            return "get html"
        elif tool_name == "read_url":
            url = tool_args.get("url", "")
            return f"read url: {url[:40]}" if url else "read url: (empty)"
        elif tool_name == "activate_skill":
            skill = tool_args.get("skill_name", "")
            return f"activate skill: {skill}" if skill else "activate skill: (empty)"
        elif tool_name == "deactivate_skill":
            skill = tool_args.get("skill_name", "")
            return f"deactivate skill: {skill}" if skill else "deactivate skill: (empty)"
        elif tool_name == "read_lark_document":
            url = tool_args.get("url", "")
            return f"read lark: {url[:40]}" if url else "read lark: (empty)"
        else:
            if tool_args:
                first_key = list(tool_args.keys())[0]
                first_val = str(tool_args[first_key])[:40]
                return f"{tool_name}: {first_key}={first_val}..."
            return f"{tool_name}"

    async def _handle_ai_content(self, chunk, thinking: str, content: str):
        """处理 AI 内容（thinking 和 content）"""
        if self.current_bot_message is None or self._expecting_new_message:
            msg = BotMessage(
                id=self._gen_id(),
                thinking_content="",
                content="",
                is_streaming=True
            )
            self.current_bot_message = BotMessageWidget(msg)
            self.on_bot_created(self.current_bot_message)
            self._expecting_new_message = False
            self._last_update_time = time.time()
            _log("Created new BotMessageWidget")

        if thinking:
            self.current_bot_message.append_thinking(thinking)
            await self._flush_update()

        if content:
            self.current_bot_message.append_content(content)
            self._accumulated_content += content

        current_time = time.time()
        if current_time - self._last_update_time > self.UPDATE_INTERVAL:
            await self._flush_update()
        else:
            self._pending_update = True

    async def _flush_update(self):
        """刷新 UI 更新"""
        if self.current_bot_message:
            self.on_bot_updated(self.current_bot_message)
        self._pending_update = False
        self._last_update_time = time.time()
        # 让出事件循环，确保 UI 能立即渲染
        await asyncio.sleep(0)

    def _extract_thinking(self, msg) -> str:
        """从消息中提取 thinking/reasoning 内容"""
        thinking = ""
        if hasattr(msg, "additional_kwargs") and msg.additional_kwargs:
            for key in ["reasoning_content", "thinking", "thought", "reasoning"]:
                if key in msg.additional_kwargs:
                    val = msg.additional_kwargs[key]
                    if isinstance(val, str):
                        thinking += val
                    elif isinstance(val, dict):
                        thinking += val.get("text", "")
        if hasattr(msg, "content") and isinstance(msg.content, list):
            for item in msg.content:
                if isinstance(item, dict):
                    item_type = item.get("type", "")
                    if item_type == "reasoning_content":
                        rc = item.get("reasoning_content", {})
                        if isinstance(rc, dict):
                            thinking += rc.get("text", "")
                        else:
                            thinking += str(rc)
                    elif item_type == "thinking":
                        thinking += item.get("thinking", "")
                    elif item_type == "reasoning":
                        thinking += item.get("text", "") or item.get("reasoning", "")
        if hasattr(msg, "reasoning_content") and msg.reasoning_content:
            if isinstance(msg.reasoning_content, str):
                thinking += msg.reasoning_content
        return thinking

    def _extract_content(self, msg) -> str:
        """从消息中提取 content 内容"""
        content = ""
        if hasattr(msg, "content"):
            if isinstance(msg.content, str):
                content = msg.content
            elif isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        content += item.get("text", "")
        return content

    def _is_error(self, result) -> bool:
        """检查结果是否包含错误 - 参考配色方案：识别 [RUN_FAILED]、[COMPLETED] 非零退出码等标记"""
        result_content = getattr(result, "content", "")
        if isinstance(result_content, str):
            first_line = result_content.splitlines()[0] if result_content else ""
            # 错误标记：[RUN_FAILED]、Error:、非零退出码、包含 ❌ 但不属于特定成功标记的情况
            is_err = (
                first_line.startswith("[RUN_FAILED]") or 
                first_line.startswith("Error:") or
                # 非零退出码视为错误 (Exit Code: X, X != 0)
                ("Exit Code:" in first_line and "Exit Code: 0" not in first_line) or
                ("❌" in first_line and not any(first_line.startswith(p) for p in
                    ["[READ_FILE]", "[CAT_FILE]", "[SEARCH_IN_FILES]",
                     "[LIST_DIR]", "[LIST_FILES]", "[SUCCESS]"]))
            )
            return is_err
        return False

    def _gen_id(self) -> str:
        """生成唯一 ID"""
        import uuid
        return str(uuid.uuid4())[:8]
