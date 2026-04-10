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
    UPDATE_INTERVAL = 0.10  # 最小更新间隔（秒）- 略微降低，让更新更频繁
    CHAR_FLUSH_THRESHOLD = 150  # 自然断点 flush 阈值 - 降低以更早 flush
    MAX_STREAM_LENGTH = 800  # 强制 flush 阈值 - 提高，与绝对上限拉开差距
    ABSOLUTE_MAX_STREAM_LENGTH = 1500  # 硬上限 - 大幅提高，只在极端情况下触发
    INCOMPLETE_CHECK_MIN_LEN = 30  # 降低最小检查长度，更快判断完整性
    FORCE_FLUSH_INTERVAL = 1.5  # 新增：强制 flush 时间间隔，避免内容滞留太久

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
        self._last_flush_time = 0  # 新增：上次 flush 时间，用于强制 flush 间隔控制
        self.token_callback = token_callback  # 保存 token 回调函数
        # 流式显示区增量更新追踪
        self._stream_displayed_text_len = 0
        self._stream_displayed_reasoning = ""

    @staticmethod
    def _normalize_markdown_for_terminal(text: str) -> str:
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
        # Markdown 表格行的特征：包含 | 分隔符，或以 | 开头/结尾
        def _looks_like_table_row(line: str) -> bool:
            stripped = line.strip()
            return stripped.startswith("|") or stripped.endswith("|") or line.count("|") >= 2

        last_nonempty_lines = []
        for line in reversed(lines):
            if line.strip():
                last_nonempty_lines.insert(0, line.strip())
            else:
                break  # 遇到空行停止

        table_lines = [l for l in last_nonempty_lines if _looks_like_table_row(l)]
        if table_lines:
            last_nonempty = last_nonempty_lines[-1] if last_nonempty_lines else ""
            if _looks_like_table_row(last_nonempty):
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
                short_cmd = cmd[:60] + ("..." if len(cmd) > 60 else "")
                display_name = f"command: {short_cmd}"
        elif tool_name == "read_file":
            path = tool_args.get("path", "")
            if path:
                display_name = f"read_file: {path}"
        elif tool_name == "search_in_files":
            keyword = tool_args.get("keyword", "")
            if keyword:
                short_kw = keyword[:40] + ("..." if len(keyword) > 40 else "")
                display_name = f"search_in_files: '{short_kw}'"
        elif tool_name == "grep_file":
            keyword = tool_args.get("keyword", "")
            if keyword:
                short_kw = keyword[:40] + ("..." if len(keyword) > 40 else "")
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
                short_paths = paths_str[:40] + ("..." if len(paths_str) > 40 else "")
                display_name = f"cat_file: {short_paths}"
        return display_name

    def _update_tool_spinner(self):
        if not self.tool_start_time or not self.current_display_tool:
            return
        elapsed = time.time() - self.tool_start_time
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]
        m, s = divmod(int(elapsed), 40)
        content = f"[dim bold cyan] {frame} {escape(self.current_display_tool)} {m:02d}:{s:02d}[/]"
        self.tool_status.update(Text.from_markup(content))

    @staticmethod
    def _has_natural_break_point(text: str) -> bool:
        """
        检查文本是否包含自然的断点，适合在此处 flush。
        自然断点包括：代码块结束、段落结束（空行）、表格结束、标题行等。
        """
        if not text:
            return False

        lines = text.split("\n")
        if len(lines) < 2:
            return False

        # 检查最后几行是否有自然断点
        last_lines = lines[-5:] if len(lines) > 5 else lines
        last_line = lines[-1].strip()
        prev_line = lines[-2].strip() if len(lines) >= 2 else ""

        # 1. 代码块结束 - 需要跟踪状态确保是真正的结束
        in_code_block = False
        code_fence_char = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence = stripped[:3]
                if not in_code_block:
                    in_code_block = True
                    code_fence_char = fence
                elif fence == code_fence_char:
                    in_code_block = False
                    code_fence_char = None
        if not in_code_block:
            for line in reversed(last_lines):
                stripped = line.strip()
                if stripped.startswith("```") or stripped.startswith("~~~"):
                    return True

        # 2. 空行（段落结束）
        if len(lines) >= 2 and last_line == "" and prev_line != "":
            return True

        # 3. 表格结束（表格行后面跟着空行）
        if len(lines) >= 2:
            if not last_line:
                prev_stripped = prev_line.strip()
                if prev_stripped.startswith("|") or prev_stripped.endswith("|") or prev_line.count("|") >= 2:
                    return True

        # 4. 标题行结束
        if last_line.startswith("#") and " " in last_line:
            header_match = re.match(r"^#{1,6}\s+", last_line)
            if header_match:
                return True

        # 5. 列表项以句子结束符结尾且长度适中
        list_pattern = r"^[\s]*([-*+]|\d+\.)\s+"
        if re.match(list_pattern, last_line):
            if last_line and last_line[-1] in ".。！?？" and len(last_line) > 20:
                return True

        # 6. 水平分割线
        if re.match(r"^[\s]*([-*_]{3,})[\s]*$", last_line):
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

        # 清空流式显示区并重置追踪状态
        self.stream_display.clear()
        self.stream_display.styles.display = "none"
        self._stream_displayed_text_len = 0
        self._stream_displayed_reasoning = ""

    def _emergency_flush(self, text: str, reasoning: str) -> tuple[str, str]:
        """
        当内容超长且 markdown 不完整时，寻找安全分割点并 flush 前缀。
        保留 suffix 继续流式显示，避免 current_response_text 无限增长导致卡顿。
        """
        if not text:
            return text, reasoning

        max_keep = 300  # 至少保留最后 300 字符继续流式显示
        search_end = max(0, len(text) - max_keep)

        # 1. 优先在段落边界（双换行）分割
        split_pos = text.rfind('\n\n', 0, search_end)
        # 2. 次选在单行边界分割
        if split_pos == -1:
            split_pos = text.rfind('\n', 0, search_end)
        # 3. 最后 resort：在 search_end 处硬切
        if split_pos == -1:
            split_pos = search_end

        if split_pos > 0:
            prefix = text[:split_pos]
            suffix = text[split_pos:].lstrip('\n')
            self.flush_to_log(prefix, reasoning)
            return suffix, ""

        return text, reasoning

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
        self._stream_displayed_text_len = 0
        self._stream_displayed_reasoning = ""

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
                        accumulated_chars = 0

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
                        snippet = content_str if len(content_str) <= max_len else content_str[
                                                                                      :max_len] + "\n... (truncated)"
                        self.main_log.write(Markdown(f"```\n{snippet}\n```"))
                    # 处理 ask_for_user 工具的 question 输出到 main_log
                    if tool_name == "ask_for_user" and content_str:
                        # 提取 [ASK_FOR_USER] 后面的 question 内容
                        if content_str.startswith("[ASK_FOR_USER] "):
                            question = content_str[len("[ASK_FOR_USER] "):].strip()
                            self.main_log.write(Text(""))
                            self.main_log.write(Text.from_markup(f"  [bold yellow]Ask:[/] {question}"))
                            self.main_log.write(Text(""))
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
                        accumulated_chars = 0

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
                time_since_flush = now - self._last_flush_time
                should_update = time_since_update > self.UPDATE_INTERVAL or accumulated_chars > 500

                # Flush 策略：
                text_len = len(current_response_text)
                has_natural_break = self._has_natural_break_point(current_response_text)
                is_incomplete = self._is_incomplete_markdown(current_response_text)

                # 1. 自然断点 + 内容足够长 -> 优雅 flush
                should_flush_at_break = (
                        text_len > self.CHAR_FLUSH_THRESHOLD and
                        has_natural_break and
                        not is_incomplete
                )
                # 2. 内容超长 -> 强制 flush（独立于 should_update）
                should_force_flush = (
                        text_len > self.MAX_STREAM_LENGTH and
                        not is_incomplete
                )
                # 3. 时间强制 flush：内容滞留太久，即使不完整也要尝试 flush
                should_time_force_flush = (
                        time_since_flush > self.FORCE_FLUSH_INTERVAL and
                        text_len > self.CHAR_FLUSH_THRESHOLD
                )

                # 0. 紧急 flush：硬上限，防止 markdown 一直不完整导致无限累积卡顿
                if text_len > self.ABSOLUTE_MAX_STREAM_LENGTH and is_incomplete:
                    current_response_text, current_reasoning_content = self._emergency_flush(
                        current_response_text, current_reasoning_content
                    )
                    accumulated_chars = len(current_reasoning_content) + len(current_response_text)
                    self._stream_displayed_text_len = 0
                    self._stream_displayed_reasoning = ""
                    self.stream_display.clear()
                    self.stream_display.styles.display = "block"
                    self._last_flush_time = now  # 更新 flush 时间
                    # 紧急 flush 后重新计算长度和状态
                    text_len = len(current_response_text)
                    has_natural_break = self._has_natural_break_point(current_response_text)
                    is_incomplete = self._is_incomplete_markdown(current_response_text)
                    # 重新计算强制 flush 条件
                    should_force_flush = (
                            text_len > self.MAX_STREAM_LENGTH and
                            not is_incomplete
                    )

                # 优先处理强制 flush（不受 should_update 限制）
                if should_force_flush or should_time_force_flush:
                    self.flush_to_log(current_response_text, current_reasoning_content)
                    current_response_text = ""
                    current_reasoning_content = ""
                    accumulated_chars = 0
                    self._stream_displayed_text_len = 0
                    self._stream_displayed_reasoning = ""
                    self.stream_display.clear()
                    self.stream_display.styles.display = "block"
                    self._last_flush_time = now
                    self.last_update_time = now
                # 自然断点 flush + UI 更新（需要 should_update）
                elif should_update and (current_reasoning_content or current_response_text):
                    # 增量更新 stream_display：推理内容变化时全量重写，否则仅追加新文本
                    reasoning_changed = current_reasoning_content != self._stream_displayed_reasoning
                    if reasoning_changed:
                        self.stream_display.clear()
                        self._stream_displayed_reasoning = current_reasoning_content
                        self._stream_displayed_text_len = 0
                        if current_reasoning_content:
                            self.stream_display.write(Text("Thinking Process.....", style="italic #565f89"))
                            for line in current_reasoning_content.split('\n'):
                                self.stream_display.write(Text(f"  {line}", style="italic #565f89"))
                            self.stream_display.write(Text(""))
                        if current_response_text:
                            self.stream_display.write(Text(current_response_text))
                            self._stream_displayed_text_len = len(current_response_text)
                    elif len(current_response_text) > self._stream_displayed_text_len:
                        new_text = current_response_text[self._stream_displayed_text_len:]
                        self.stream_display.write(Text(new_text))
                        self._stream_displayed_text_len = len(current_response_text)

                    self.last_update_time = now
                    self._pending_scroll = True

                    # 自然断点 flush（更频繁但优雅）
                    if should_flush_at_break:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""
                        accumulated_chars = 0
                        self._stream_displayed_text_len = 0
                        self._stream_displayed_reasoning = ""
                        self.stream_display.clear()
                        self.stream_display.styles.display = "block"
                        self._last_flush_time = now

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
            self._last_flush_time = time.time()  # 重置 flush 时间
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
