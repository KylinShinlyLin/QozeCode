# tui_components/messages/stream_handler.py
import asyncio
import time
import json
import sys
import os
from typing import Callable, Optional, Dict
from datetime import datetime
from langchain_core.messages import AIMessage, ToolMessage as LC_ToolMessage

from .types import BotMessage, ToolMessage, ToolStatus
from .bot_widget import BotMessageWidget

# 日志文件路径
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

        self._current_bot_message = None
        self._active_tools: Dict[str, dict] = {}
        self._last_update_time = 0
        self._update_interval = 0.05
        self._accumulated_content = ""
        self._expecting_new_message = False
        self._accumulated_ai_message = None
        self._pending_update = False

    def reset(self):
        self._current_bot_message = None
        self._active_tools.clear()
        self._last_update_time = 0
        self._accumulated_content = ""
        self._expecting_new_message = False
        self._accumulated_ai_message = None
        self._pending_update = False

    async def process_stream(self, stream):
        _log("=" * 60)
        _log("Stream started")
        self.reset()
        chunk_count = 0

        try:
            async for message_chunk, metadata in stream:
                chunk_count += 1
                chunk_type = type(message_chunk).__name__

                try:
                    # 处理 AIMessage
                    if isinstance(message_chunk, AIMessage) or chunk_type in ["AIMessageChunk", "AIMessage"]:
                        if chunk_count <= 5:
                            _log(f"Chunk {chunk_count}: {chunk_type}")
                            if hasattr(message_chunk, 'additional_kwargs'):
                                _log(f"  additional_kwargs: {message_chunk.additional_kwargs}")
                            if hasattr(message_chunk, 'content'):
                                _log(f"  content type: {type(message_chunk.content)}")
                                _log(f"  content: {str(message_chunk.content)[:200]}")

                        thinking = self._extract_thinking(message_chunk)
                        content = self._extract_content(message_chunk)

                        if thinking:
                            _log(f"  >>> THINKING ({len(thinking)} chars): '{thinking[:100]}...'")

                        if self._accumulated_ai_message is None:
                            self._accumulated_ai_message = message_chunk
                        else:
                            self._accumulated_ai_message += message_chunk

                        await self._handle_ai_chunk(message_chunk, thinking, content)

                        if self._accumulated_ai_message.tool_calls:
                            _log(f"  Processing {len(self._accumulated_ai_message.tool_calls)} tool_calls")
                            await self._handle_tool_calls(self._accumulated_ai_message.tool_calls)
                            self._accumulated_ai_message = None

                    elif isinstance(message_chunk, LC_ToolMessage) or chunk_type in ["ToolMessageChunk", "ToolMessage"]:
                        await self._handle_tool_result(message_chunk)
                        self._accumulated_ai_message = None

                except Exception as e:
                    _log(f"ERROR chunk {chunk_count}: {e}")
                    import traceback
                    _log(traceback.format_exc())

        except Exception as e:
            _log(f"Fatal error: {e}")
            import traceback
            _log(traceback.format_exc())
            raise

        if self._pending_update and self._current_bot_message:
            self._flush_update()

        if self.on_stream_complete:
            estimated_tokens = int(len(self._accumulated_content) * 0.3)
            self.on_stream_complete(estimated_tokens)

        _log(f"Stream ended, chunks={chunk_count}")
        _log("=" * 60)

    def _flush_update(self):
        if self._current_bot_message:
            self.on_bot_updated(self._current_bot_message)
        self._pending_update = False
        self._last_update_time = time.time()

    async def _handle_ai_chunk(self, chunk, thinking: str, content: str):
        if self._current_bot_message is None or self._expecting_new_message:
            if self._current_bot_message and self._expecting_new_message:
                pass  # 保持之前的消息

            msg = BotMessage(
                id=self._gen_id(),
                thinking_content="",
                content="",
                is_streaming=True
            )
            self._current_bot_message = BotMessageWidget(msg)
            self.on_bot_created(self._current_bot_message)
            self._expecting_new_message = False
            self._last_update_time = time.time()
            _log(f"Created new BotMessageWidget")

        # 使用 append 方法更新 thinking
        if thinking:
            self._current_bot_message.append_thinking(thinking)
            _log(f"  Appended thinking: {len(thinking)} chars")
            # 立即刷新
            self._flush_update()

        # 使用 append 方法更新 content
        if content:
            self._current_bot_message.append_content(content)
            self._accumulated_content += content

        current_time = time.time()
        should_update = (current_time - self._last_update_time > self._update_interval)

        if should_update:
            self._flush_update()
        else:
            self._pending_update = True

    def _extract_thinking(self, msg) -> str:
        thinking = ""
        
        # 检查 additional_kwargs
        if hasattr(msg, "additional_kwargs") and msg.additional_kwargs:
            for key in ["reasoning_content", "thinking", "thought", "reasoning"]:
                if key in msg.additional_kwargs:
                    val = msg.additional_kwargs[key]
                    if isinstance(val, str):
                        thinking += val
                    elif isinstance(val, dict):
                        thinking += val.get("text", "")

        # 检查 content list
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
                    elif "reasoning" in item:
                        r = item.get("reasoning")
                        if isinstance(r, dict):
                            thinking += r.get("text", "")
                        elif isinstance(r, str):
                            thinking += r

        # 检查 reasoning_content 属性
        if hasattr(msg, "reasoning_content") and msg.reasoning_content:
            if isinstance(msg.reasoning_content, str):
                thinking += msg.reasoning_content
        
        return thinking

    def _extract_content(self, msg) -> str:
        content = ""
        if hasattr(msg, "content"):
            if isinstance(msg.content, str):
                content = msg.content
            elif isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        content += item.get("text", "")
        return content

    def _get_tool_args(self, tc: dict) -> dict:
        args = tc.get("args", {})
        if args:
            return args

        func = tc.get("function", {})
        if isinstance(func, dict):
            args_str = func.get("arguments", "")
            if args_str:
                try:
                    return json.loads(args_str)
                except json.JSONDecodeError:
                    pass
            args = func.get("args", {})
            if args:
                return args

        return {}

    async def _handle_tool_calls(self, tool_calls: list):
        _log(f"Tool calls: {len(tool_calls)}")
        if self._current_bot_message:
            pass

        self._expecting_new_message = True

        for tc in tool_calls:
            tool_call_id = tc.get("id", "")
            tool_name = tc.get("name", "unknown")
            tool_args = self._get_tool_args(tc)

            display_name = self._format_tool_name(tool_name, tool_args)
            _log(f"  Tool: {tool_name}, display={display_name}")

            is_update = tool_call_id in self._active_tools

            if not is_update and self.on_tool_started:
                self.on_tool_started(tool_call_id, display_name)

            self._active_tools[tool_call_id] = {
                "name": tool_name,
                "display_name": display_name
            }

    async def _handle_tool_result(self, result):
        tc_id = getattr(result, 'tool_call_id', 'unknown')
        _log(f"Tool result: id={tc_id[:20]}...")

        tool_info = self._active_tools.pop(tc_id, None)

        if not tool_info and self._active_tools:
            if len(self._active_tools) == 1:
                _id, _info = list(self._active_tools.items())[0]
                tool_info = _info
                self._active_tools.clear()
            else:
                _id, _info = list(self._active_tools.items())[-1]
                tool_info = _info
                del self._active_tools[_id]

        if not tool_info:
            tool_info = {"name": "Tool", "display_name": "run: unknown"}

        is_error = self._is_error(result)
        _log(f"  display_name={tool_info['display_name']}, is_error={is_error}")

        if self.on_tool_completed:
            self.on_tool_completed(tc_id, tool_info["display_name"], is_error)

    def _format_tool_name(self, name: str, args: dict) -> str:
        if name == "execute_command":
            cmd = args.get("command", "")
            return "run: " + cmd[:60] + ("..." if len(cmd) > 60 else "")
        elif name == "read_file":
            return "read: " + args.get("path", "")
        elif name == "cat_file":
            paths = args.get("paths", "")
            return "cat: " + str(paths)[:60]
        elif name == "tavily_search":
            return "search: '" + args.get("query", "")[:60] + "'"
        elif name == "browser_navigate":
            return "navigate: " + args.get("url", "")[:50]
        elif name == "browser_click":
            return "click: " + args.get("selector", "")[:50]
        elif name == "browser_type":
            return "type: " + args.get("text", "")[:30]
        elif name == "browser_read_page":
            return "read page"
        elif name == "browser_get_html":
            return "get html"
        elif name == "read_url":
            return "read url: " + args.get("url", "")[:40]
        elif name == "activate_skill":
            return "activate skill: " + args.get("skill_name", "")
        elif name == "deactivate_skill":
            return "deactivate skill: " + args.get("skill_name", "")
        elif name == "read_lark_document":
            return "read lark: " + args.get("url", "")[:40]
        else:
            return f"run: {name}"

    def _is_error(self, result) -> bool:
        content = getattr(result, "content", "")
        if isinstance(content, str):
            return "error" in content.lower()
        return False

    def _gen_id(self) -> str:
        import uuid
        return str(uuid.uuid4())[:8]
