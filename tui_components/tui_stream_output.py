# -*- coding: utf-8 -*-
"""
TUIStreamOutput - 优化版本 v2
修复了代码块和表格被截断导致的渲染问题

主要优化点：
1. 使用列表存储 chunks，避免 O(n²) 字符串拷贝
2. 增量 markdown 检测，只检查尾部新增内容
3. 批量 UI 更新，减少 clear/write 频率
4. 结构化内容保护（代码块、表格不被截断）
"""
import re
import time
import asyncio
import traceback
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
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


@dataclass
class MarkdownState:
    """跟踪 Markdown 结构状态"""
    in_code_block: bool = False
    code_fence_char: str = ""  # ``` 或 ~~~
    in_table: bool = False
    table_start_line: int = 0

    def copy(self) -> 'MarkdownState':
        return MarkdownState(
            in_code_block=self.in_code_block,
            code_fence_char=self.code_fence_char,
            in_table=self.in_table,
            table_start_line=self.table_start_line
        )


class TUIStreamOutput:
    """流式输出适配器 - 性能优化版 v2"""

    UPDATE_INTERVAL = 0.15
    CHAR_FLUSH_THRESHOLD = 300  # 增加阈值，给更多时间完成结构
    MAX_STREAM_LENGTH = 500  # 增加阈值
    HARD_MAX_STREAM_LENGTH = 3000
    INCOMPLETE_CHECK_MIN_LEN = 100
    UI_BATCH_SIZE = 3

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

        self._buffer = StreamBuffer()
        self._update_counter = 0

        # 跟踪 markdown 状态
        self._markdown_state = MarkdownState()
        self._pending_code_block_closure = False  # 标记是否需要补全代码块

    @staticmethod
    def _normalize_markdown_for_terminal(text: str) -> str:
        """规范化 Markdown"""
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

    def _analyze_markdown_state(self, text: str) -> MarkdownState:
        """
        分析文本的 Markdown 结构状态
        返回代码块、表格等结构是否处于打开状态
        """
        state = MarkdownState()
        lines = text.split('\n')

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 代码块检测
            if stripped.startswith('```') or stripped.startswith('~~~'):
                fence = stripped[:3]
                if not state.in_code_block:
                    state.in_code_block = True
                    state.code_fence_char = fence
                elif fence == state.code_fence_char:
                    state.in_code_block = False
                    state.code_fence_char = ""
                continue

            # 表格检测（只在不在代码块中时）
            if not state.in_code_block and '|' in stripped:
                pipe_count = stripped.count('|')
                if pipe_count >= 2:
                    # 判断是否是表格分隔行 |---|---|
                    is_separator = re.match(r'^\|?[\s\-:|]+\|?', stripped)
                    if not is_separator and not state.in_table:
                        # 可能是表格开始
                        state.in_table = True
                        state.table_start_line = i
                elif state.in_table and not stripped:
                    # 空行结束表格
                    state.in_table = False

        return state

    def _find_safe_flush_point(self, text: str, max_len: int) -> Tuple[int, bool, str]:
        """
        寻找安全的 flush 断点

        返回: (flush_point, needs_closure, closure_text)
        - flush_point: 安全的截断位置
        - needs_closure: 是否需要补全结构
        - closure_text: 需要追加的闭合文本
        """
        if len(text) <= max_len:
            return len(text), False, ""

        state = self._analyze_markdown_state(text[:max_len])

        # 如果在代码块中，尝试找到代码块结束
        if state.in_code_block:
            # 向前查找代码块结束
            lines = text[max_len:].split('\n')
            for i, line in enumerate(lines):
                if line.strip().startswith(state.code_fence_char):
                    # 找到了代码块结束，可以在此之后 flush
                    end_pos = max_len + sum(len(lines[j]) + 1 for j in range(i + 1))
                    return end_pos, False, ""

            # 代码块未结束，尝试在 max_len 之前找代码块开始
            lines = text[:max_len].split('\n')
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip().startswith(state.code_fence_char):
                    # 找到了代码块开始，在此之前 flush
                    flush_point = sum(len(lines[j]) + 1 for j in range(i))
                    return flush_point, False, ""

            # 找不到好的断点，强制 flush 并补全代码块
            return max_len, True, f"\n{state.code_fence_char}"

        # 如果在表格中，尝试找到表格结束
        if state.in_table:
            # 向前查找空行（表格结束标记）
            remaining = text[max_len:]
            empty_line_match = re.search(r'\n\s*\n', remaining)
            if empty_line_match:
                end_pos = max_len + empty_line_match.start() + 1
                return end_pos, False, ""

            # 表格未结束，在 max_len 之前找表格开始
            lines = text[:max_len].split('\n')
            for i in range(len(lines) - 1, -1, -1):
                if not lines[i].strip().count('|') >= 2:
                    # 找到了表格前的非表格行
                    flush_point = sum(len(lines[j]) + 1 for j in range(i + 1))
                    return flush_point, False, ""

        # 查找自然断点（空行）
        lines = text[:max_len].split('\n')
        for i in range(len(lines) - 1, max(0, len(lines) - 20), -1):
            if not lines[i].strip():
                flush_point = sum(len(lines[j]) + 1 for j in range(i))
                return flush_point, False, ""

        # 找不到好的断点，直接在 max_len 处截断
        return max_len, False, ""

    def _is_safe_to_flush(self, text: str) -> Tuple[bool, bool, str]:
        """
        检查当前状态是否可以安全 flush

        返回: (is_safe, needs_closure, closure_text)
        """
        if not text or len(text) < self.INCOMPLETE_CHECK_MIN_LEN:
            return False, False, ""

        state = self._analyze_markdown_state(text)

        # 如果在代码块中，不安全
        if state.in_code_block:
            # 检查是否接近代码块结束
            tail = text[-500:]
            if state.code_fence_char in tail:
                # 可能快要结束了，等一等
                return False, False, ""
            return False, False, ""

        # 如果在表格中，检查表格是否完整
        if state.in_table:
            lines = text.split('\n')
            table_lines = []
            for line in reversed(lines):
                if not line.strip():
                    break
                if '|' in line:
                    table_lines.insert(0, line)

            # 表格至少需要有表头和分隔行
            if len(table_lines) < 2:
                return False, False, ""

            # 检查分隔行格式
            separator = table_lines[1] if len(table_lines) > 1 else ""
            if not re.match(r'^\|?[\s\-:|]+\|?$', separator.strip()):
                return False, False, ""

        # 检查行内代码
        if text.count('`') % 2 != 0:
            return False, False, ""

        return True, False, ""

    @staticmethod
    def _get_tool_display_name(tool_name: str, tool_args: dict) -> str:
        """获取工具显示名称"""
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
        """更新工具 spinner"""
        if not self.tool_start_time or not self.current_display_tool:
            return
        elapsed = time.time() - self.tool_start_time
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]
        m, s = divmod(int(elapsed), 60)
        content = f"[dim bold cyan] {frame} {escape(self.current_display_tool)} {m:02d}:{s:02d}[/]"
        self.tool_status.update(Text.from_markup(content))

    def flush_to_log(self, text: str, reasoning: str, closure_text: str = ""):
        """
        将累积的内容刷新到主日志

        Args:
            text: 要 flush 的文本
            reasoning: reasoning 内容
            closure_text: 需要追加的闭合文本（如 ```）
        """
        if reasoning:
            reasoning_clean = reasoning.strip()
            content = Text(reasoning_clean, style="italic #909090")
            self.main_log.write(Padding(content, (0, 0, 1, 2)))

        if text:
            # 如果需要补全结构，先加上
            if closure_text:
                text = text + closure_text

            normalized_text = self._normalize_markdown_for_terminal(text)
            self.main_log.write(Markdown(normalized_text))

        self.main_log.scroll_end(animate=False)
        self.stream_display.clear()
        self.stream_display.styles.display = "none"

    def _should_update_ui(self, now: float, force: bool = False) -> bool:
        """判断是否应该更新 UI"""
        if force:
            return True

        time_since_update = now - self.last_update_time
        if time_since_update < self.UPDATE_INTERVAL:
            return False

        self._update_counter += 1
        if self._update_counter < self.UI_BATCH_SIZE:
            return False

        self._update_counter = 0
        return True

    def _render_stream_display(self):
        """渲染流式显示区"""
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
        self._markdown_state = MarkdownState()

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

                    # Flush 当前缓冲区（ToolMessage 是强制 flush 点）
                    if self._buffer.text_length > 0 or self._buffer.reasoning_length > 0:
                        text = self._buffer.get_text()
                        reasoning = self._buffer.get_reasoning()

                        # 查找安全断点
                        if len(text) > self.CHAR_FLUSH_THRESHOLD:
                            flush_point, needs_closure, closure = self._find_safe_flush_point(
                                text, self.CHAR_FLUSH_THRESHOLD
                            )
                            if flush_point < len(text):
                                text_to_flush = text[:flush_point]
                                remaining = text[flush_point:]
                            else:
                                text_to_flush = text
                                remaining = ""
                                needs_closure = False
                                closure = ""

                            self.flush_to_log(text_to_flush, reasoning, closure if needs_closure else "")

                            # 如果有剩余内容，保留在缓冲区
                            self._buffer.clear()
                            if remaining:
                                self._buffer.add_text(remaining)
                        else:
                            self.flush_to_log(text, reasoning)
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

                    # Tool 结果展示
                    content_str = str(message_chunk.content)
                    first_line = content_str.splitlines()[0] if content_str else ""
                    is_error = first_line.startswith("[RUN_FAILED]") or first_line.startswith("Error:") or \
                               ("❌" in first_line and not any(first_line.startswith(p) for p in
                                                              ["[READ_FILE]", "[CAT_FILE]", "[SEARCH_IN_FILES]",
                                                               "[LIST_DIR]", "[LIST_FILES]"]))

                    status_icon = "✗" if is_error else "✓"
                    color = "red" if is_error else "cyan"
                    icon_color = "red" if is_error else "green"

                    if tool_name == "read_file" and content_str:
                        max_len = 4000
                        snippet = content_str if len(content_str) <= max_len else content_str[
                                                                                      :max_len] + "\n... (truncated)"
                        self.main_log.write(Markdown(f"```\n{snippet}\n```"))

                    error_hint = ""
                    if is_error:
                        error_line = next((line for line in content_str.splitlines()
                                           if
                                           line.startswith("[RUN_FAILED]") or line.startswith("Error:") or "❌" in line),
                                          first_line)
                        error_hint = f" - {escape(error_line[:140])}"

                    final_msg = f"  [dim bold {icon_color}]{status_icon}[/][dim bold {color}] {escape(tool_name)} in {elapsed:.2f}s{error_hint}[/]"
                    self.main_log.write(Text.from_markup(final_msg))
                    continue

                # 处理 Tool Calls
                if accumulated_ai_message and accumulated_ai_message.tool_calls:
                    # 强制 flush 当前内容
                    if self._buffer.text_length > 0 or self._buffer.reasoning_length > 0:
                        text = self._buffer.get_text()
                        reasoning = self._buffer.get_reasoning()

                        # 查找安全断点
                        flush_point, needs_closure, closure = self._find_safe_flush_point(
                            text, len(text)
                        )
                        if flush_point > 0:
                            text_to_flush = text[:flush_point]
                            remaining = text[flush_point:]
                            self.flush_to_log(text_to_flush, reasoning, closure if needs_closure else "")

                            self._buffer.clear()
                            if remaining:
                                self._buffer.add_text(remaining)
                        else:
                            self.flush_to_log(text, reasoning)
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

                # Flush 策略（使用结构感知检测）
                text_len = self._buffer.text_length

                if text_len > self.CHAR_FLUSH_THRESHOLD:
                    text = self._buffer.get_text()

                    # 检查是否可以安全 flush
                    is_safe, needs_closure, closure = self._is_safe_to_flush(text)

                    # 检查是否超过硬上限
                    force_flush = text_len > self.HARD_MAX_STREAM_LENGTH

                    if is_safe or force_flush:
                        if force_flush and not is_safe:
                            # 强制 flush，需要找安全断点
                            flush_point, needs_closure, closure = self._find_safe_flush_point(
                                text, self.HARD_MAX_STREAM_LENGTH
                            )
                            text_to_flush = text[:flush_point]
                            remaining = text[flush_point:]
                        else:
                            text_to_flush = text
                            remaining = ""

                        reasoning = self._buffer.get_reasoning()
                        self.flush_to_log(text_to_flush, reasoning, closure if needs_closure else "")

                        self._buffer.clear()
                        if remaining:
                            self._buffer.add_text(remaining)

                        self.stream_display.styles.display = "block"

            # 最终 flush
            final_text = self._buffer.get_text()
            final_reasoning = self._buffer.get_reasoning()

            # 如果最后还有未闭合的代码块，补全它
            state = self._analyze_markdown_state(final_text)
            closure = ""
            if state.in_code_block:
                closure = f"\n{state.code_fence_char}"

            self.flush_to_log(final_text, final_reasoning, closure)

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
