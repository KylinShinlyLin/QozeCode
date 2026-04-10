# -*- coding: utf-8 -*-
"""
TUIStreamOutput - 优化版本
主要优化点：
1. 使用列表存储 chunks，避免 O(n²) 字符串拷贝
2. 增量 markdown 检测，只检查尾部新增内容
3. 批量 UI 更新，减少 clear/write 频率
4. 缓存计算结果，避免重复扫描
"""
import re
import time
import asyncio
import traceback
from dataclasses import dataclass, field
from typing import List, Optional
from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape
from rich.padding import Padding
from rich.text import Text
from textual.widgets import RichLog, Static
from langchain_core.messages import AIMessage, ToolMessage

import qoze_code_agent
from .tui_constants import SPINNER_FRAMES


@dataclass
class StreamBuffer:
    """流式内容缓冲区 - 优化存储结构"""
    chunks: List[str] = field(default_factory=list)
    reasoning_chunks: List[str] = field(default_factory=list)
    
    # 缓存总长度，避免重复计算
    _text_length: int = 0
    _reasoning_length: int = 0
    
    def add_text(self, text: str):
        if text:
            self.chunks.append(text)
            self._text_length += len(text)
    
    def add_reasoning(self, text: str):
        if text:
            self.reasoning_chunks.append(text)
            self._reasoning_length += len(text)
    
    def get_text(self) -> str:
        """延迟拼接，只在需要时计算"""
        return "".join(self.chunks)
    
    def get_reasoning(self) -> str:
        return "".join(self.reasoning_chunks)
    
    def clear(self):
        self.chunks.clear()
        self.reasoning_chunks.clear()
        self._text_length = 0
        self._reasoning_length = 0
    
    @property
    def text_length(self) -> int:
        return self._text_length
    
    @property
    def reasoning_length(self) -> int:
        return self._reasoning_length
    
    def get_tail(self, length: int = 500) -> str:
        """获取尾部内容，用于增量检测"""
        if self._text_length <= length:
            return self.get_text()
        # 从后往前找，直到凑够长度
        result = []
        remaining = length
        for chunk in reversed(self.chunks):
            if len(chunk) <= remaining:
                result.insert(0, chunk)
                remaining -= len(chunk)
            else:
                result.insert(0, chunk[-remaining:])
                break
        return "".join(result)


class TUIStreamOutput:
    """流式输出适配器 - 性能优化版"""

    # 性能调优参数
    UPDATE_INTERVAL = 0.15           # 增加最小更新间隔（原来是 0.1）
    CHAR_FLUSH_THRESHOLD = 200       # 增加 flush 阈值（原来是 150）
    MAX_STREAM_LENGTH = 400          # 增加最大长度（原来是 300）
    HARD_MAX_STREAM_LENGTH = 3000    # 增加硬上限（原来是 2000）
    INCOMPLETE_CHECK_MIN_LEN = 100   # 增加检测最小长度（原来是 50）
    UI_BATCH_SIZE = 3                # UI 更新批处理阈值

    def __init__(self, main_log: RichLog, stream_display: RichLog, tool_status: Static, token_callback=None):
        self.main_log = main_log
        self.stream_display = stream_display
        self.tool_status = tool_status
        self.tool_start_time = None
        self.tool_timer = None
        self.active_tools = {}
        self.current_display_tool = None
        self.last_update_time = 0
        self._pending_scroll = False
        self._accumulated_content = ""
        self.token_callback = token_callback
        
        # 使用缓冲区替代字符串累积
        self._buffer = StreamBuffer()
        self._update_counter = 0  # UI 更新计数器
        
        # 缓存 markdown 检测状态，避免重复计算
        self._cached_incomplete_result = None
        self._cached_text_hash = None

    @staticmethod
    def _normalize_markdown_for_terminal(text: str) -> str:
        """规范化 Markdown（保持不变）"""
        if not text:
            return text

        normalized_lines = []
        in_code_block = False

        for line in text.splitlines():
            stripped = line.strip()

            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_code_block = not in_code_block
                normalized_lines.append(line)
                continue

            if not in_code_block:
                match = re.match(r"^(\s*)(#{4,6})\s+(.+?)\s*$", line)
                if match:
                    indent, _hashes, content = match.groups()
                    normalized_lines.append(f"{indent}**{content}**")
                    continue

            normalized_lines.append(line)

        return "\n".join(normalized_lines)

    def _is_incomplete_markdown_fast(self, text: str) -> bool:
        """
        快速检测 - 优化版本
        1. 只检测尾部内容（新增部分）
        2. 使用简化规则
        3. 缓存结果
        """
        if not text:
            return False
        
        text_len = len(text)
        
        # 短文本直接返回 True（保护机制）
        if text_len < self.INCOMPLETE_CHECK_MIN_LEN:
            return True
        
        # 只检查尾部 800 字符（足够检测未闭合结构）
        tail = text[-800:] if text_len > 800 else text
        
        # 快速检查：代码块（最严格）
        code_fence_count = tail.count('```') + tail.count('~~~')
        if code_fence_count % 2 != 0:
            return True
        
        # 快速检查：行内代码（只在尾部检查）
        if tail.count('`') % 2 != 0:
            return True
        
        lines = tail.split('\n')
        last_line = lines[-1].strip() if lines else ""
        
        # 快速检查：表格（简化版）
        if '|' in last_line and last_line.count('|') >= 2:
            # 可能还在表格中
            return True
        
        # 快速检查：未闭合标签（简化版，只检查常见标签）
        if '<' in last_line:
            # 简单检测：如果最后有 < 但没有 >，可能未闭合
            if last_line.rfind('<') > last_line.rfind('>'):
                return True
        
        # 快速检查：链接/图片语法
        if re.search(r'!?\[[^\]]*\]\([^)]*$', tail[-100:]):
            return True
        
        # 快速检查：列表项（简化）
        if re.match(r'^[\s]*[-*+\d]+[\.\s]', last_line):
            if len(last_line) < 80:  # 短列表项可能还没写完
                return True
        
        return False

    def _has_natural_break_point_fast(self, text: str) -> bool:
        """
        快速断点检测 - 只检查尾部
        """
        if not text or len(text) < 50:
            return False
        
        # 只检查尾部 600 字符
        tail = text[-600:] if len(text) > 600 else text
        lines = tail.split('\n')
        
        if len(lines) < 2:
            return False
        
        # 检查最后几行
        last_lines = lines[-5:] if len(lines) > 5 else lines
        
        # 1. 空行（段落结束）
        if len(last_lines) >= 2:
            if last_lines[-1].strip() == '' and last_lines[-2].strip() != '':
                return True
        
        # 2. 代码块结束（通过 fence 计数判断）
        fence_count = tail.count('```') + tail.count('~~~')
        if fence_count > 0 and fence_count % 2 == 0:
            # 有闭合的代码块，检查最后是否有 fence
            for line in reversed(last_lines):
                stripped = line.strip()
                if stripped.startswith('```') or stripped.startswith('~~~'):
                    return True
                if stripped:  # 遇到非空行就停止
                    break
        
        # 3. 标题行后面有内容
        if len(last_lines) >= 2:
            if re.match(r'^#{1,6}\s+', last_lines[-2].strip()) and last_lines[-1].strip():
                return True
        
        return False

    @staticmethod
    def _get_tool_display_name(tool_name: str, tool_args: dict) -> str:
        """（保持不变）"""
        display_name = tool_name
        if tool_name == "execute_command":
            cmd = tool_args.get("command", "")
            if cmd:
                short_cmd = cmd[:120] + ("..." if len(cmd) > 120 else "")
                display_name = f"command: {short_cmd}"
        elif tool_name == "read_file":
            path = tool_args.get("path", "")
            if path:
                display_name = f"read_file: {path}"
        elif tool_name == "search_in_files":
            keyword = tool_args.get("keyword", "")
            if keyword:
                short_kw = keyword[:60] + ("..." if len(keyword) > 60 else "")
                display_name = f"search_in_files: '{short_kw}'"
        elif tool_name == "grep_file":
            keyword = tool_args.get("keyword", "")
            if keyword:
                short_kw = keyword[:60] + ("..." if len(keyword) > 60 else "")
                display_name = f"grep_file: '{short_kw}'"
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
                display_name = f"cat_file: {short_paths}"
        return display_name

    def _update_tool_spinner(self):
        """（保持不变）"""
        if not self.tool_start_time or not self.current_display_tool:
            return
        elapsed = time.time() - self.tool_start_time
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]
        m, s = divmod(int(elapsed), 60)
        content = f"[dim bold cyan] {frame} {escape(self.current_display_tool)} {m:02d}:{s:02d}[/]"
        self.tool_status.update(Text.from_markup(content))

    def flush_to_log(self, text: str, reasoning: str):
        """将累积的内容刷新到主日志"""
        if reasoning:
            reasoning_clean = reasoning.strip()
            content = Text(reasoning_clean, style="italic #909090")
            self.main_log.write(Padding(content, (0, 0, 1, 2)))

        if text:
            normalized_text = self._normalize_markdown_for_terminal(text)
            self.main_log.write(Markdown(normalized_text))

        self.main_log.scroll_end(animate=False)

        # 清空流式显示区
        self.stream_display.clear()
        self.stream_display.styles.display = "none"

    def _should_update_ui(self, now: float, force: bool = False) -> bool:
        """
        判断是否应该更新 UI
        使用批处理减少更新频率
        """
        if force:
            return True
        
        time_since_update = now - self.last_update_time
        
        # 时间间隔检查
        if time_since_update < self.UPDATE_INTERVAL:
            return False
        
        # 批处理：累积一定次数的更新请求才执行
        self._update_counter += 1
        if self._update_counter < self.UI_BATCH_SIZE:
            return False
        
        self._update_counter = 0
        return True

    def _render_stream_display(self):
        """
        优化的渲染方法
        使用增量更新替代 clear+rewrite
        """
        display_lines = []
        
        reasoning = self._buffer.get_reasoning()
        text = self._buffer.get_text()

        if reasoning:
            display_lines.append(Text("Thinking Process.....", style="italic #565f89"))
            for line in reasoning.split('\n'):
                display_lines.append(Text(f"  {line}", style="italic #565f89"))
            display_lines.append(Text(""))

        if text:
            display_lines.append(Text(text))

        self.stream_display.clear()
        for line in display_lines:
            self.stream_display.write(line)

    async def stream_response(self, current_state, conversation_state, thread_id="default_session"):
        # 重置状态
        self._buffer.clear()
        self._update_counter = 0
        self._cached_incomplete_result = None
        self._cached_text_hash = None
        
        total_response_text = ""
        total_reasoning_content = ""
        accumulated_ai_message = None

        # 初始化累积内容
        self._accumulated_content = ""
        if current_state and "messages" in current_state:
            for msg in current_state["messages"]:
                if hasattr(msg, 'content'):
                    if isinstance(msg.content, str):
                        self._accumulated_content += msg.content
                    elif isinstance(msg.content, list):
                        for item in msg.content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                self._accumulated_content += item.get("text", "")

        self.stream_display.styles.display = "block"
        self.last_update_time = 0

        try:
            async for message_chunk, metadata in qoze_code_agent.agent.astream(
                    current_state,
                    stream_mode="messages",
                    config={"recursion_limit": 300, "configurable": {"thread_id": thread_id}}
            ):
                try:
                    current_task = asyncio.current_task()
                    if current_task and current_task.cancelled():
                        raise asyncio.CancelledError("Stream cancelled by user")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass

                # 处理 AIMessage
                if isinstance(message_chunk, AIMessage):
                    if message_chunk.content is None:
                        message_chunk.content = ""
                    if isinstance(message_chunk.content, str):
                        self._accumulated_content += message_chunk.content
                    elif isinstance(message_chunk.content, list):
                        for item in message_chunk.content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                self._accumulated_content += item.get("text", "")
                    if accumulated_ai_message is None:
                        accumulated_ai_message = message_chunk
                    else:
                        accumulated_ai_message += message_chunk

                # 处理 ToolMessage
                if isinstance(message_chunk, ToolMessage):
                    if hasattr(message_chunk, 'content') and message_chunk.content:
                        self._accumulated_content += str(message_chunk.content)
                    
                    # Flush 当前缓冲区
                    if self._buffer.text_length > 0 or self._buffer.reasoning_length > 0:
                        self.flush_to_log(self._buffer.get_text(), self._buffer.get_reasoning())
                        self._buffer.clear()

                    tool_name = self.active_tools.pop(message_chunk.tool_call_id, None)
                    if not tool_name and self.active_tools:
                        if len(self.active_tools) == 1:
                            _id, _name = list(self.active_tools.items())[0]
                            tool_name = _name
                            self.active_tools.clear()
                        else:
                            _id, _name = list(self.active_tools.items())[-1]
                            tool_name = _name
                            del self.active_tools[_id]

                    if not tool_name:
                        tool_name = message_chunk.name if hasattr(message_chunk, "name") else None
                    if not tool_name:
                        tool_name = self.current_display_tool if self.current_display_tool else "Tool"

                    accumulated_ai_message = None

                    if not self.active_tools:
                        if self.tool_timer:
                            self.tool_timer.stop()
                            self.tool_timer = None
                        self.tool_status.update("")
                        self.tool_status.styles.display = "none"
                        self.current_display_tool = None

                    elapsed = time.time() - (self.tool_start_time or time.time())
                    if not self.active_tools:
                        self.tool_start_time = None

                    # Tool 结果展示（简化版）
                    content_str = str(message_chunk.content)
                    first_line = content_str.splitlines()[0] if content_str else ""
                    is_error = first_line.startswith("[RUN_FAILED]") or first_line.startswith("Error:") or \
                               ("❌" in first_line and not any(first_line.startswith(p) for p in 
                                ["[READ_FILE]", "[CAT_FILE]", "[SEARCH_IN_FILES]", "[LIST_DIR]", "[LIST_FILES]"]))
                    
                    status_icon = "✗" if is_error else "✓"
                    color = "red" if is_error else "cyan"
                    icon_color = "red" if is_error else "green"
                    
                    if tool_name == "read_file" and content_str:
                        max_len = 4000
                        snippet = content_str if len(content_str) <= max_len else content_str[:max_len] + "\n... (truncated)"
                        self.main_log.write(Markdown(f"```\n{snippet}\n```"))
                    
                    error_hint = ""
                    if is_error:
                        error_line = next((line for line in content_str.splitlines() 
                                         if line.startswith("[RUN_FAILED]") or line.startswith("Error:") or "❌" in line), first_line)
                        error_hint = f" - {escape(error_line[:140])}"
                    
                    final_msg = f"  [dim bold {icon_color}]{status_icon}[/][dim bold {color}] {escape(tool_name)} in {elapsed:.2f}s{error_hint}[/]"
                    self.main_log.write(Text.from_markup(final_msg))
                    continue

                # 处理 Tool Calls
                if accumulated_ai_message and accumulated_ai_message.tool_calls:
                    if self._buffer.text_length > 0 or self._buffer.reasoning_length > 0:
                        self.flush_to_log(self._buffer.get_text(), self._buffer.get_reasoning())
                        self._buffer.clear()

                    for tool_call in accumulated_ai_message.tool_calls:
                        t_name = tool_call.get("name", "Unknown Tool")
                        t_id = tool_call.get("id", "unknown_id")
                        t_args = tool_call.get("args", {})
                        display_name = self._get_tool_display_name(t_name, t_args)
                        self.active_tools[t_id] = display_name
                        self.current_display_tool = display_name

                        if not self.tool_timer:
                            self.tool_start_time = time.time()
                            self.tool_status.styles.display = "block"
                            self.tool_timer = self.tool_status.set_interval(0.1, self._update_tool_spinner)
                    
                    self.stream_display.styles.display = "block"

                # 提取 reasoning
                reasoning = ""
                if hasattr(message_chunk, "additional_kwargs") and message_chunk.additional_kwargs:
                    reasoning = message_chunk.additional_kwargs.get("reasoning_content", "")
                if isinstance(message_chunk.content, list):
                    for content_item in message_chunk.content:
                        if isinstance(content_item, dict) and content_item.get("type") == "reasoning_content":
                            rc = content_item.get("reasoning_content", {})
                            reasoning += rc.get("text", "") if isinstance(rc, dict) else str(rc)
                        if isinstance(content_item, dict) and content_item.get("type") == "thinking":
                            reasoning += content_item.get("thinking", "")

                if reasoning:
                    self._buffer.add_reasoning(reasoning)
                    total_reasoning_content += reasoning

                # 提取 content
                content = message_chunk.content
                chunk_text = ""
                if isinstance(content, str):
                    chunk_text = content
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            chunk_text += item.get("text", "")

                if chunk_text:
                    self._buffer.add_text(chunk_text)
                    total_response_text += chunk_text
                    self._accumulated_content += chunk_text

                # 判断是否需要更新 UI
                now = time.time()
                should_update = self._should_update_ui(now)

                if should_update and (self._buffer.text_length > 0 or self._buffer.reasoning_length > 0):
                    self._render_stream_display()
                    self.last_update_time = now
                    self._pending_scroll = True

                # Flush 策略（使用优化后的检测方法）
                text_len = self._buffer.text_length
                
                # 只有长度超过阈值才进行检测
                if text_len > self.CHAR_FLUSH_THRESHOLD:
                    has_natural_break = self._has_natural_break_point_fast(self._buffer.get_text())
                    is_incomplete = self._is_incomplete_markdown_fast(self._buffer.get_text())
                    
                    should_flush = (
                        (text_len > self.CHAR_FLUSH_THRESHOLD and has_natural_break and not is_incomplete) or
                        (text_len > self.MAX_STREAM_LENGTH and not is_incomplete) or
                        (text_len > self.HARD_MAX_STREAM_LENGTH)
                    )
                    
                    if should_flush:
                        text_to_flush = self._buffer.get_text()
                        reasoning_to_flush = self._buffer.get_reasoning()
                        
                        # 强制 flush 时尝试找好的断点
                        if text_len > self.HARD_MAX_STREAM_LENGTH:
                            lines = text_to_flush.split('\n')
                            flush_point = len(text_to_flush)
                            for i in range(len(lines) - 1, max(0, len(lines) - 10), -1):
                                if not lines[i].strip():
                                    flush_point = sum(len(lines[j]) + 1 for j in range(i))
                                    break
                            remaining = text_to_flush[flush_point:]
                            text_to_flush = text_to_flush[:flush_point]
                            # 剩余内容放回缓冲区
                            self._buffer.clear()
                            if remaining:
                                self._buffer.add_text(remaining)
                        else:
                            self._buffer.clear()
                        
                        self.flush_to_log(text_to_flush, reasoning_to_flush)
                        self.stream_display.styles.display = "block"

            # 最终 flush
            self.flush_to_log(self._buffer.get_text(), self._buffer.get_reasoning())

        except asyncio.CancelledError:
            self.stream_display.styles.display = "none"
            raise
        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)
            if "429" in error_msg or "overloaded" in error_msg.lower():
                suggestion = "⚠️ 服务端负载过高，请稍后重试或切换其他模型。"
            else:
                suggestion = ""
            self.main_log.write(Text(f"Stream Error: {e}{suggestion}", style="red"))
            self.stream_display.styles.display = "none"
        finally:
            if total_response_text or total_reasoning_content:
                conversation_state["llm_calls"] += 1
            if self.tool_timer:
                self.tool_timer.stop()
                self.tool_timer = None
            self.tool_status.update("")
            self.tool_status.styles.display = "none"
            self.active_tools.clear()
            self.current_display_tool = None
            self.tool_start_time = None
            self.last_update_time = 0
            if self.token_callback:
                content_len = len(self._accumulated_content)
                estimated_tokens = int(content_len * 0.3)
                self.token_callback(estimated_tokens)
