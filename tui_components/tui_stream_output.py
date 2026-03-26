# -*- coding: utf-8 -*-
import re
import time
import asyncio
import traceback
from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape
from rich.padding import Padding
from rich.text import Text
from textual.widgets import RichLog, Static
from langchain_core.messages import AIMessage, ToolMessage

import qoze_code_agent
from .tui_constants import SPINNER_FRAMES


class TUIStreamOutput:
    """流式输出适配器 - 优化版"""

    # 性能调优参数
    UPDATE_INTERVAL = 0.15  # 最小更新间隔（秒）
    CHAR_FLUSH_THRESHOLD = 300  # 字符数阈值，避免频繁 flush
    MAX_STREAM_LENGTH = 2000  # stream_display 最大长度，超过则强制 flush
    INCOMPLETE_CHECK_MIN_LEN = 100  # 只有文本超过此长度才检查 markdown 完整性

    def __init__(self, main_log: RichLog, stream_display: RichLog, tool_status: Static, token_callback=None):
        self.main_log = main_log
        self.stream_display = stream_display
        self.tool_status = tool_status
        self.tool_start_time = None
        self.tool_timer = None
        self.active_tools = {}
        self.current_display_tool = None
        self.last_update_time = 0
        self._pending_scroll = False  # 防抖标记
        self._accumulated_content = ""  # 累积的内容用于 token 估算
        self.token_callback = token_callback  # 保存 token 回调函数

    def _normalize_markdown_for_terminal(self, text: str) -> str:
        """
        规范化 Markdown，减少 Rich 在终端中对深层标题的块状渲染带来的“漂浮/居中感”。
        - 保留 h1/h2/h3
        - 将 h4/h5/h6 转成加粗正文，保持更稳定的左对齐视觉
        - 代码块内部内容不做处理
        """
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

    def _is_incomplete_markdown(self, text: str) -> bool:
        """
        检测当前文本是否处于未完成的 Markdown 结构中。
        优化：只有文本超过一定长度才执行完整检查，减少正则开销。
        """
        if not text:
            return False

        text_len = len(text)
        lines = text.split('\n')

        # 检查代码块状态 - 必须完整扫描所有行
        # 如果只检查最后20行，长代码块（>20行）会被误判为已结束
        in_code_block = False
        code_fence_char = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('```') or stripped.startswith('~~~'):
                fence = stripped[:3]
                if not in_code_block:
                    in_code_block = True
                    code_fence_char = fence
                elif fence == code_fence_char:
                    in_code_block = False
                    code_fence_char = None

        if in_code_block:
            return True

        # 短文本直接认为不完整（避免过早 flush 导致格式错乱）
        if text_len < self.INCOMPLETE_CHECK_MIN_LEN:
            return True

        # 检查行内代码是否成对（只检查最后 500 字符）
        last_chunk = text[-500:] if text_len > 500 else text
        if last_chunk.count('`') % 2 != 0:
            return True

        # 检查链接或图片语法是否完整（只检查最后 200 字符）
        tail = text[-200:] if text_len > 200 else text
        if re.search(r'!?\[[^\]]*\]\([^)]*$', tail):
            return True

        # 检查表格是否完整 - 表格需要以空行结束才算完整
        # Markdown 表格行的特征：至少包含两个 |（单元格分隔符）
        last_nonempty_lines = []
        for line in reversed(lines):
            if line.strip():
                last_nonempty_lines.insert(0, line.strip())
            else:
                break  # 遇到空行停止
        
        # 检查是否有表格行
        table_lines = [l for l in last_nonempty_lines if l.count("|") >= 2]
        if table_lines:
            # 如果最后非空行包含 |，说明表格可能还未结束（需要空行才算结束）
            last_nonempty = last_nonempty_lines[-1] if last_nonempty_lines else ""
            if last_nonempty.count("|") >= 2:
                return True

        # 检查列表是否可能未完成（只检查最后一行）
        last_line = lines[-1].strip() if lines else ""
        if re.match(r'^[\s]*[-*+][\s]', last_line) or re.match(r'^[\s]*\d+\.[\s]', last_line):
            if len(last_line) < 50:
                return True

        return False

    @staticmethod
    def _get_tool_display_name(tool_name: str, tool_args: dict) -> str:
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
        if not self.tool_start_time or not self.current_display_tool:
            return
        elapsed = time.time() - self.tool_start_time
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]
        m, s = divmod(int(elapsed), 60)
        content = f"[dim bold cyan] {frame} {escape(self.current_display_tool)} {m:02d}:{s:02d}[/]"
        self.tool_status.update(Text.from_markup(content))

    def _has_natural_break_point(self, text: str) -> bool:
        """
        检查文本是否包含自然的断点，适合在此处 flush。
        自然断点包括：代码块结束、段落结束（空行）、表格结束、标题行等。
        """
        if not text:
            return False

        lines = text.split('\n')
        if len(lines) < 2:
            return False

        # 检查最后几行是否有自然断点
        last_lines = lines[-5:] if len(lines) > 5 else lines

        # 1. 代码块结束 - 需要跟踪状态确保是真正的结束
        in_code_block = False
        code_fence_char = None
        for line in lines:  # 完整扫描跟踪状态
            stripped = line.strip()
            if stripped.startswith('```') or stripped.startswith('~~~'):
                fence = stripped[:3]
                if not in_code_block:
                    in_code_block = True
                    code_fence_char = fence
                elif fence == code_fence_char:
                    in_code_block = False
                    code_fence_char = None
        # 如果不在代码块中且最后几行有 ```，说明代码块刚结束
        if not in_code_block:
            for line in reversed(last_lines):
                stripped = line.strip()
                if stripped.startswith('```') or stripped.startswith('~~~'):
                    return True

        # 2. 空行（段落结束）
        if len(lines) >= 2 and lines[-1].strip() == '' and lines[-2].strip() != '':
            return True

        # 3. 表格结束（表格行后面跟着空行）
        # Markdown 表格需要空行来明确结束，否则 flush 时可能截断
        if len(lines) >= 2:
            last_line = lines[-1].strip()
            prev_line = lines[-2].strip()
            # 当前行是空行，且前一行是表格行
            if not last_line and prev_line.count("|") >= 2:
                return True

        # 4. 标题行（以 # 开头）后面有内容
        if len(lines) >= 2:
            last_line = lines[-1].strip()
            prev_line = lines[-2].strip()
            if re.match(r'^#{1,6}\s+', prev_line) and last_line:
                return True

        return False

    def flush_to_log(self, text: str, reasoning: str):
        """将累积的内容刷新到主日志，清空流式显示区"""
        if reasoning:
            reasoning_clean = reasoning.strip()
            # 使用灰色斜体，左缩进2个字符
            content = Text(reasoning_clean, style="italic #909090")
            self.main_log.write(Padding(content, (0, 0, 1, 2)))

        if text:
            normalized_text = self._normalize_markdown_for_terminal(text)
            self.main_log.write(Markdown(normalized_text))

        self.main_log.scroll_end(animate=False)

        # 清空流式显示区
        self.stream_display.clear()
        self.stream_display.styles.display = "none"

    async def stream_response(self, current_state, conversation_state, thread_id="default_session"):
        current_response_text = ""
        current_reasoning_content = ""
        total_response_text = ""
        total_reasoning_content = ""
        accumulated_ai_message = None

        # 使用字符数而非行数作为阈值，更准确
        accumulated_chars = 0

        # 重置累积内容，并添加当前状态中的用户消息
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

                if isinstance(message_chunk, ToolMessage):
                    if hasattr(message_chunk, 'content') and message_chunk.content:
                        self._accumulated_content += str(message_chunk.content)
                    if current_response_text or current_reasoning_content:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""
                        accumulated_lines = 0

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

                    content_str = str(message_chunk.content)
                    first_line = content_str.splitlines()[0] if content_str else ""
                    success_prefixes = (
                        "[READ_FILE]",
                        "[CAT_FILE]",
                        "[SEARCH_IN_FILES]",
                        "[LIST_DIR]",
                        "[LIST_FILES]",
                    )
                    is_error = False
                    if first_line.startswith("[RUN_FAILED]") or first_line.startswith("Error:"):
                        is_error = True
                    elif "❌" in first_line and not first_line.startswith(success_prefixes):
                        is_error = True
                    status_icon = "✗" if is_error else "✓"
                    color = "red" if is_error else "cyan"
                    icon_color = "red" if is_error else "green"
                    if tool_name == "read_file" and content_str:
                        max_len = 4000
                        snippet = content_str if len(content_str) <= max_len else content_str[:max_len] + "\n... (truncated)"
                        self.main_log.write(Markdown(f"```\n{snippet}\n```"))
                    error_hint = ""
                    if is_error:
                        error_line = ""
                        for line in content_str.splitlines():
                            if line.startswith("[RUN_FAILED]") or line.startswith("Error:") or "❌" in line:
                                error_line = line
                                break
                        if not error_line:
                            error_line = first_line
                        if error_line:
                            error_hint = f" - {escape(error_line[:140])}"
                    final_msg = f"  [dim bold {icon_color}]{status_icon}[/][dim bold {color}] {escape(tool_name)} in {elapsed:.2f}s{error_hint}[/]"
                    self.main_log.write(Text.from_markup(final_msg))
                    continue

                if accumulated_ai_message and accumulated_ai_message.tool_calls:
                    if current_response_text or current_reasoning_content:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""
                        accumulated_lines = 0

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
                    current_reasoning_content += reasoning
                    total_reasoning_content += reasoning
                    accumulated_chars += len(reasoning)

                content = message_chunk.content
                chunk_text = ""
                if isinstance(content, str):
                    chunk_text = content
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            chunk_text += item.get("text", "")

                if chunk_text:
                    current_response_text += chunk_text
                    total_response_text += chunk_text
                    accumulated_chars += len(chunk_text)
                    self._accumulated_content += chunk_text

                now = time.time()
                time_since_update = now - self.last_update_time
                should_update = time_since_update > self.UPDATE_INTERVAL or accumulated_chars > 500

                # Flush 策略：
                # 1. 内容过长时，寻找自然断点 flush
                # 2. 内容超长时强制 flush（即使 markdown 不完整）
                text_len = len(current_response_text)
                has_natural_break = self._has_natural_break_point(current_response_text)
                is_incomplete = self._is_incomplete_markdown(current_response_text)

                # 自然断点 + 内容足够长 -> 优雅 flush
                should_flush_at_break = (
                    text_len > self.CHAR_FLUSH_THRESHOLD and
                    has_natural_break and
                    not is_incomplete
                )
                # 内容超长 -> 强制 flush
                should_force_flush = (
                    text_len > self.MAX_STREAM_LENGTH and
                    not is_incomplete
                )

                if should_update and (current_reasoning_content or current_response_text):
                    display_lines = []

                    if current_reasoning_content:
                        display_lines.append(Text("Thinking Process.....", style="italic #565f89"))
                        for line in current_reasoning_content.split('\n'):
                            display_lines.append(Text(f"  {line}", style="italic #565f89"))
                        display_lines.append(Text(""))

                    if current_response_text:
                        display_lines.append(Text(current_response_text))

                    self.stream_display.clear()
                    for line in display_lines:
                        self.stream_display.write(line)

                    self.last_update_time = now
                    self._pending_scroll = True

                    # 优先处理自然断点 flush（更频繁但优雅）
                    if should_flush_at_break:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""
                        accumulated_chars = 0
                        self.stream_display.styles.display = "block"
                    # 强制 flush（超长内容）
                    elif should_force_flush:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""
                        accumulated_chars = 0
                        self.stream_display.styles.display = "block"

            self.flush_to_log(current_response_text, current_reasoning_content)

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
