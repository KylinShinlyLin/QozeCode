#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流式输出模块 - 负责 AI 响应的流式输出和状态管理
"""
import sys

from colorama import init
from langchain_core.messages import AIMessage, ToolMessage
from rich.console import Console
from rich.live import Live
from rich.progress import Progress, TextColumn, TimeElapsedColumn

from shared_console import console


# init(autoreset=True)


class StreamOutput:
    def __init__(self, agent):
        self.agent = agent
        # self.local_sessions = local_sessions
        # 创建独立的 console 实例用于流式输出
        self.stream_console = Console(
            file=sys.stdout,
            force_terminal=True,
            width=None,
            height=None
        )
        # ANSI 颜色代码
        self.CYAN = "\033[96m"
        self.CYAN_THINK = "\033[38;2;144;238;144m"
        self.LIGHT_GRAY = "\033[90m"
        self.GREEN = "\033[92m"
        self.RESET = "\033[0m"
        self.WHITE = "\033[97m"

    async def stream_text_with_color(self, text, style="white", delay=0.03):
        """逐字符流式输出带颜色的文本"""
        for char in text:
            self.stream_console.print(char, style=style, end="")

    # async def stream_text_with_color(self, text, color="cyan", delay=0.03):
    #     """逐字符流式输出带颜色的文本"""
    #     for char in text:
    #         if color:
    #             sys.stdout.write(f"{color} {char} {self.RESET}")
    #         else:
    #             sys.stdout.write(char)
    #         sys.stdout.flush()  # 立即刷新输出
    #         await asyncio.sleep(delay)

    # async def stream_response(self, model_name, current_state, conversation_state):
    #     """处理 AI 流式响应"""
    #     current_response_text = ""  # 当前流式响应的文本
    #     current_reasoning_content = ""  # 推理内容
    #     need_point = True
    #     need_point_think = True
    #     has_response = False
    #
    #     # with (Progress(
    #     #         TextColumn("[bold blue]{task.description}"),
    #     #         TimeElapsedColumn(),
    #     #         console=console,
    #     #         transient=False
    #     # ) as progress):
    #     #     task = progress.add_task(f"{self.CYAN}Generating.....{self.RESET}", total=None)
    #     # print(f"current_state={current_state}")
    #
    #     with Live(refresh_per_second=4, vertical_overflow="visible") as live:
    #         async for message_chunk, metadata in self.agent.astream(
    #                 current_state, stream_mode="messages", config={"recursion_limit": 150}
    #         ):
    #             # 跳过 ToolMessage 类型
    #             if isinstance(message_chunk, ToolMessage):
    #                 continue
    #             # print(message_chunk)
    #             # 处理 DeepSeek 推理内容
    #             if hasattr(message_chunk, 'additional_kwargs') and message_chunk.additional_kwargs:
    #                 reasoning_content = message_chunk.additional_kwargs.get('reasoning_content', '')
    #                 if reasoning_content:
    #                     has_response = True
    #                     current_reasoning_content += reasoning_content
    #                     # print(
    #                     #     f"{self.CYAN}- thinking:{self.RESET} {self.LIGHT_GRAY}{reasoning_content}{self.RESET}" if need_point_think else f"{self.LIGHT_GRAY}{reasoning_content}{self.RESET}",
    #                     #     end='')
    #
    #                     # print(f"{self.LIGHT_GRAY}{reasoning_content}{self.RESET}", end='')
    #                     live.update(f"[dim]{current_reasoning_content}[/dim]")
    #                     live.refresh()
    #                     need_point_think = False
    #                     continue
    #
    #             # 处理 Gemini 推理内容
    #             if isinstance(message_chunk.content, list):
    #                 for content_item in message_chunk.content:
    #                     if isinstance(content_item, dict):
    #                         # Gemini 推理内容处理
    #                         if content_item.get('type') == 'thinking':
    #                             reasoning_content = content_item.get('thinking', '')
    #                             if reasoning_content:
    #                                 has_response = True
    #                                 current_reasoning_content += reasoning_content
    #                                 # print(
    #                                 #     f"{self.LIGHT_GRAY}{thinking_content}{self.RESET}" if need_point_think else f"{self.LIGHT_GRAY}{thinking_content}{self.RESET}",
    #                                 #     end='')
    #
    #                                 # print(f"{self.LIGHT_GRAY}{reasoning_content}{self.RESET}", end='')
    #                                 live.update(f"[dim]{current_reasoning_content}[/dim]")
    #                                 live.refresh()
    #                                 need_point_think = False
    #                             continue
    #
    #             # 普通文本处理
    #             if message_chunk.content:
    #                 chunk_text = ''
    #                 if isinstance(message_chunk.content, list):
    #                     for content_item in message_chunk.content:
    #                         if isinstance(content_item, dict) and 'type' in content_item and content_item.get(
    #                                 'type') == 'text':
    #                             text_content = content_item.get('text', '')
    #                             chunk_text += text_content
    #                 elif isinstance(message_chunk.content, str):
    #                     text_content = message_chunk.content
    #                     chunk_text += text_content
    #
    #                 if chunk_text != '':
    #                     has_response = True
    #                     # if need_point and "qwen" in model_name:
    #                     #     print(f"\n{self.CYAN}● {self.RESET}", end='')
    #                     # elif need_point:
    #                     #     print("\n", end='')
    #                     #     print(f"{self.CYAN}● {self.RESET}", end='')
    #                     need_point = False
    #                     # print(chunk_text, end="")
    #
    #                     current_response_text += chunk_text
    #                     live.update(f"[dim]{current_reasoning_content}[/dim]\n[white]{current_response_text}[/white]")
    #
    #             if hasattr(message_chunk, 'response_metadata') and message_chunk.response_metadata:
    #                 if 'finish_reason' in message_chunk.response_metadata:
    #                     # if has_response and "qwen" in model_name:
    #                     #     print("\n", end='')
    #                     has_response = False
    #                     continue
    #
    #     # 保存最终状态
    #     # progress.stop_task(task)
    #     # progress.update(task, description=f"[bold green]✓ {self.CYAN}Completed{self.RESET}")
    #
    #     additional_kwargs = {'reasoning_content': current_reasoning_content}
    #
    #     ai_response = AIMessage(
    #         content=current_response_text,
    #         additional_kwargs=additional_kwargs)
    #     conversation_state["messages"].extend([ai_response])
    #     conversation_state["llm_calls"] += 1

    async def stream_response(self, model_name, current_state, conversation_state):
        """处理 AI 流式响应"""
        current_response_text = ""
        current_reasoning_content = ""
        has_response = False

        with Live(refresh_per_second=10, vertical_overflow="visible") as live:  # 提高刷新率
            async for message_chunk, metadata in self.agent.astream(
                    current_state, stream_mode="messages", config={"recursion_limit": 150}
            ):
                if isinstance(message_chunk, ToolMessage):
                    continue

                chunk_processed = False  # 添加标志防止重复处理

                # 处理 DeepSeek 推理内容
                if hasattr(message_chunk, 'additional_kwargs') and message_chunk.additional_kwargs:
                    reasoning_content = message_chunk.additional_kwargs.get('reasoning_content', '')
                    if reasoning_content:
                        has_response = True
                        current_reasoning_content += reasoning_content
                        # 立即更新显示（流式效果）
                        live.update(f"[dim]{current_reasoning_content}[/dim]")
                        chunk_processed = True
                        continue  # 重要：处理完推理内容后直接跳到下一个chunk

                # 只有当不是推理内容时才处理文本内容
                if not chunk_processed and message_chunk.content:
                    text_to_add = ""

                    if isinstance(message_chunk.content, list):
                        for content_item in message_chunk.content:
                            if isinstance(content_item, dict):
                                # Gemini 推理内容处理
                                if content_item.get('type') == 'thinking':
                                    thinking_content = content_item.get('thinking', '')
                                    if thinking_content:
                                        has_response = True
                                        current_reasoning_content += thinking_content
                                        live.update(f"[dim]{current_reasoning_content}[/dim]")
                                        chunk_processed = True
                                # Gemini/其他模型的文本内容
                                elif content_item.get('type') == 'text':
                                    text_content = content_item.get('text', '')
                                    text_to_add += text_content
                    elif isinstance(message_chunk.content, str):
                        text_to_add = message_chunk.content

                    # 处理普通文本内容
                    if text_to_add and not chunk_processed:
                        has_response = True
                        current_response_text += text_to_add

                        # 构建完整显示内容
                        display_content = ""
                        if current_reasoning_content:
                            display_content += f"[dim]{current_reasoning_content}[/dim]\n"
                        display_content += f"[white]{current_response_text}[/white]"

                        # 立即更新显示（流式效果）
                        live.update(display_content)

                # 处理结束标志
                if hasattr(message_chunk, 'response_metadata') and message_chunk.response_metadata:
                    if 'finish_reason' in message_chunk.response_metadata:
                        has_response = False

        # 保存最终状态
        additional_kwargs = {'reasoning_content': current_reasoning_content}
        ai_response = AIMessage(
            content=current_response_text,
            additional_kwargs=additional_kwargs
        )
        conversation_state["messages"].extend([ai_response])
        conversation_state["llm_calls"] += 1
