# tui_components/messages/stream_handler.py
import asyncio
import time
import json
from typing import Callable, Optional, Dict
from datetime import datetime
from langchain_core.messages import AIMessage, ToolMessage as LC_ToolMessage

from .types import BotMessage, ToolMessage, ToolStatus
from .bot_widget import BotMessageWidget


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
        self._update_interval = 0.1
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
        self.reset()
        chunk_count = 0
        last_yield_time = time.time()
        
        try:
            async for message_chunk, metadata in stream:
                chunk_count += 1
                current_time = time.time()
                
                if current_time - last_yield_time > 5:
                    await asyncio.sleep(0)
                    last_yield_time = current_time
                
                try:
                    if isinstance(message_chunk, AIMessage):
                        if self._accumulated_ai_message is None:
                            self._accumulated_ai_message = message_chunk
                        else:
                            self._accumulated_ai_message += message_chunk
                        
                        await self._handle_ai_chunk(message_chunk)
                        
                        if self._accumulated_ai_message.tool_calls:
                            await self._handle_tool_calls(self._accumulated_ai_message.tool_calls)
                            self._accumulated_ai_message = None
                    
                    elif isinstance(message_chunk, LC_ToolMessage):
                        await self._handle_tool_result(message_chunk)
                        self._accumulated_ai_message = None
                        
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                
                if chunk_count % 50 == 0 and self._pending_update:
                    self._flush_update()
                    
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise
        
        if self._pending_update and self._current_bot_message:
            self._flush_update()
        
        if self.on_stream_complete:
            estimated_tokens = int(len(self._accumulated_content) * 0.3)
            self.on_stream_complete(estimated_tokens)
    
    def _flush_update(self):
        if self._current_bot_message:
            self.on_bot_updated(self._current_bot_message)
        self._pending_update = False
        self._last_update_time = time.time()
    
    async def _handle_ai_chunk(self, chunk: AIMessage):
        thinking = self._extract_thinking(chunk)
        content = self._extract_content(chunk)
        
        if self._current_bot_message is None or self._expecting_new_message:
            if self._current_bot_message and self._expecting_new_message:
                self._current_bot_message.is_streaming = False
                self._flush_update()
            
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
        
        if thinking:
            self._current_bot_message.thinking_content += thinking
        
        if content:
            self._current_bot_message.content += content
            self._accumulated_content += content
        
        current_time = time.time()
        should_update = (current_time - self._last_update_time > self._update_interval)
        
        if should_update or thinking:
            self._flush_update()
        else:
            self._pending_update = True
    
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
        if self._current_bot_message:
            self._current_bot_message.is_streaming = False
            self._flush_update()
        
        self._expecting_new_message = True
        
        for tc in tool_calls:
            tool_call_id = tc.get("id", "")
            tool_name = tc.get("name", "unknown")
            tool_args = self._get_tool_args(tc)
            
            display_name = self._format_tool_name(tool_name, tool_args)
            
            is_update = tool_call_id in self._active_tools
            
            if not is_update and self.on_tool_started:
                self.on_tool_started(tool_call_id, display_name)
            
            self._active_tools[tool_call_id] = {
                'name': tool_name,
                'display_name': display_name
            }
    
    async def _handle_tool_result(self, result: LC_ToolMessage):
        tc_id = result.tool_call_id
        
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
            tool_info = {'name': 'Tool', 'display_name': 'run: unknown'}
        
        is_error = self._is_error(result)
        
        if self.on_tool_completed:
            self.on_tool_completed(tc_id, tool_info['display_name'], is_error)
    
    def _extract_thinking(self, msg: AIMessage) -> str:
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
        content = ""
        if isinstance(msg.content, str):
            content = msg.content
        elif isinstance(msg.content, list):
            for item in msg.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    content += item.get("text", "")
        return content
    
    def _format_tool_name(self, name: str, args: dict) -> str:
        if name == "execute_command":
            cmd = args.get("command", "")
            return "run: " + cmd[:60] + ("..." if len(cmd) > 60 else "")
        elif name == "read_file":
            return "read: " + args.get("path", "")
        elif name == "cat_file":
            paths = args.get
("paths", "")
            return "cat: " + str(paths)[:60]
        elif name == "tavily_search":
            return "search: '" + args.get("query", "")[:60] + "'"
        elif name == "browser_navigate":
            return "browser: " + args.get("url", "")[:60] + "..."
        elif name == "grep_file":
            return "grep: '" + args.get("keyword", "")[:60] + "'"
        elif name == "search_in_files":
            return "search: '" + args.get("keyword", "")[:60] + "'"
        elif name == "list_directory":
            return "ls: " + args.get("path", ".")
        elif name == "list_files":
            return "ls: " + args.get("path", ".")
        elif name == "write_file":
            return "write: " + args.get("path", "")
        elif name == "ask_for_user":
            return "ask: '" + args.get("question", "")[:60] + "'"
        elif name == "activate_skill":
            return "skill: " + args.get("skill_name", "")
        elif name == "list_available_skills":
            return "skills: list"
        elif name == "deactivate_skill":
            return "skill: deactivate " + args.get("skill_name", "")
        elif name == "get_skill_install_guide":
            return "skill: install " + args.get("skill_name", "")
        else:
            return name
    
    def _is_error(self, result: LC_ToolMessage) -> bool:
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
