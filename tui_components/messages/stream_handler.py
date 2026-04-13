# tui_components/messages/stream_handler.py
import time
from typing import Callable, Optional, Dict
from datetime import datetime
from langchain_core.messages import AIMessage, ToolMessage

from .types import BotMessage, ToolMessage, ToolStatus
from .bot_widget import BotMessageWidget
from .tool_widget import ToolMessageWidget


class MessageStreamHandler:
    """消息流处理器 - 协调三种消息的流式展示"""
    
    def __init__(self,
                 on_bot_created: Callable[[BotMessageWidget], None],
                 on_bot_updated: Callable[[BotMessageWidget], None],
                 on_tool_created: Callable[[ToolMessageWidget], None],
                 on_tool_updated: Callable[[ToolMessageWidget], None],
                 on_stream_complete: Optional[Callable[[int], None]] = None):
        
        self.on_bot_created = on_bot_created
        self.on_bot_updated = on_bot_updated
        self.on_tool_created = on_tool_created
        self.on_tool_updated = on_tool_updated
        self.on_stream_complete = on_stream_complete
        
        # 这些状态会在每次 process_stream 时重置
        self._current_bot_message: Optional[BotMessageWidget] = None
        self._active_tools: Dict[str, ToolMessageWidget] = {}
        self._last_update_time = 0
        self._update_interval = 0.05
        self._accumulated_content = ""
    
    def reset(self):
        """重置状态，准备处理新的请求"""
        self._current_bot_message = None
        self._active_tools = {}
        self._last_update_time = 0
        self._accumulated_content = ""
    
    async def process_stream(self, stream):
        """处理 LangGraph 流式输出"""
        # 每次处理新流时重置状态
        self.reset()
        
        accumulated = None
        
        try:
            async for chunk, metadata in stream:
                try:
                    if isinstance(chunk, AIMessage):
                        await self._handle_ai_chunk(chunk, accumulated)
                        accumulated = chunk if accumulated is None else accumulated + chunk
                    
                    elif isinstance(chunk, ToolMessage):
                        await self._handle_tool_result(chunk)
                        accumulated = None
                    
                    if accumulated and accumulated.tool_calls:
                        await self._handle_tool_calls(accumulated.tool_calls)
                        accumulated = None
                        
                except Exception as e:
                    import logging
                    logging.error(f"Error processing chunk: {e}", exc_info=True)
                    continue
            
            # 流完成，计算 token
            if self.on_stream_complete:
                estimated_tokens = int(len(self._accumulated_content) * 0.3)
                self.on_stream_complete(estimated_tokens)
                
        except Exception as e:
            import logging
            logging.error(f"Stream processing error: {e}", exc_info=True)
            raise
    
    async def _handle_ai_chunk(self, chunk: AIMessage, accumulated):
        """处理 AI 消息片段"""
        thinking = self._extract_thinking(chunk)
        content = self._extract_content(chunk)
        
        # 创建新的 BotMessage（如果是第一条）
        if self._current_bot_message is None:
            msg = BotMessage(
                id=self._gen_id(),
                thinking_content="",
                content="",
                is_streaming=True
            )
            self._current_bot_message = BotMessageWidget(msg)
            self.on_bot_created(self._current_bot_message)
        
        # 节流更新
        current_time = time.time()
        should_update = (current_time - self._last_update_time > self._update_interval)
        
        if thinking:
            self._current_bot_message.thinking_content += thinking
        
        if content:
            self._current_bot_message.content += content
            self._accumulated_content += content
        
        if should_update or content or thinking:
            self.on_bot_updated(self._current_bot_message)
            self._last_update_time = current_time
    
    async def _handle_tool_calls(self, tool_calls: list):
        """处理工具调用请求"""
        # 完成当前的 BotMessage
        if self._current_bot_message:
            self._current_bot_message.is_streaming = False
            self.on_bot_updated(self._current_bot_message)
            self._current_bot_message = None
        
        # 创建 ToolMessage 组件
        for tc in tool_calls:
            msg = ToolMessage(
                id=self._gen_id(),
                tool_name=tc.get("name", "unknown"),
                tool_args=tc.get("args", {}),
                tool_call_id=tc.get("id", ""),
                display_name=self._format_tool_name(tc),
                status=ToolStatus.RUNNING
            )
            widget = ToolMessageWidget(msg)
            self._active_tools[msg.tool_call_id] = widget
            self.on_tool_created(widget)
    
    async def _handle_tool_result(self, result: ToolMessage):
        """处理工具执行结果"""
        tc_id = result.tool_call_id
        
        # 尝试匹配工具调用 ID
        if tc_id not in self._active_tools:
            if self._active_tools:
                tc_id = list(self._active_tools.keys())[-1]
            else:
                import logging
                logging.warning(f"Tool result for unknown tool_call_id: {tc_id}")
                return
        
        widget = self._active_tools[tc_id]
        
        # 判断成功/失败
        is_error = self._is_error(result)
        new_status = ToolStatus.ERROR if is_error else ToolStatus.SUCCESS
        
        # 状态转换
        widget.transition_to(
            new_status,
            result_content=str(result.content) if not is_error else "",
            error_message=str(result.content) if is_error else None,
            elapsed_time=widget.elapsed_time
        )
        self.on_tool_updated(widget)
        
        # 从活跃工具中移除
        if tc_id in self._active_tools:
            del self._active_tools[tc_id]
    
    def _extract_thinking(self, msg: AIMessage) -> str:
        """提取 thinking 内容"""
        thinking = ""
        if hasattr(msg, "additional_kwargs") and msg.additional_kwargs:
            thinking = msg.additional_kwargs.get("reasoning_content", "")
        if isinstance(msg.content, list):
            for item in msg.content:
                if isinstance(item, dict):
                    if item.get("type") == "reasoning_content":
                        rc = item.get("reasoning_content", {})
                        thinking += rc.get("text", "") if isinstance(rc, dict) else str(rc)
                    elif item.get("type") == "thinking":
                        thinking += item.get("thinking", "")
        return thinking
    
    def _extract_content(self, msg: AIMessage) -> str:
        """提取正式 content"""
        content = ""
        if isinstance(msg.content, str):
            content = msg.content
        elif isinstance(msg.content, list):
            for item in msg.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    content += item.get("text", "")
        return content
    
    def _format_tool_name(self, tc: dict) -> str:
        """格式化工具展示名称"""
        name = tc.get("name", "unknown")
        args = tc.get("args", {})
        
        formatters = {
            "execute_command": lambda a: f"run: {a.get('command', '')[:50]}...",
            "read_file": lambda a: f"read: {a.get('path', '')}",
            "cat_file": lambda a: f"cat: {str(a.get('paths', ''))[:50]}",
            "tavily_search": lambda a: f"search: '{a.get('query', '')[:40]}'",
            "browser_navigate": lambda a: f"browser: {a.get('url', '')[:50]}...",
            "grep_file": lambda a: f"grep: '{a.get('keyword', '')[:40]}'",
            "search_in_files": lambda a: f"search: '{a.get('keyword', '')[:40]}'",
            "list_directory": lambda a: f"ls: {a.get('path', '.')}",
            "list_files": lambda a: f"ls: {a.get('path', '.')}",
            "write_file": lambda a: f"write: {a.get('path', '')}",
            "ask_for_user": lambda a: f"ask: '{a.get('question', '')[:40]}'",
            "activate_skill": lambda a: f"skill: {a.get('skill_name', '')}",
            "list_available_skills": lambda a: "skills: list",
            "deactivate_skill": lambda a: f"skill: deactivate {a.get('skill_name', '')}",
            "get_skill_install_guide": lambda a: f"skill: install {a.get('skill_name', '')}",
        }
        return formatters.get(name, lambda a: name)(args)
    
    def _is_error(self, result: ToolMessage) -> bool:
        """判断工具执行是否失败"""
        content = str(result.content)
        return (
            content.startswith("[RUN_FAILED]") or
            content.startswith("Error:") or
            ("❌" in content and not any(
                content.startswith(p) for p in ["[READ_FILE]", "[CAT_FILE]", "[SEARCH_IN_FILES]"]
            ))
        )
    
    def _gen_id(self) -> str:
        import uuid
        return str(uuid.uuid4())
