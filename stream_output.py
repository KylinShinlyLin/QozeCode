#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流式输出模块 - 负责 AI 响应的流式输出和状态管理
"""

from langchain_core.messages import AIMessage, ToolMessage
from rich.progress import Progress, TextColumn, TimeElapsedColumn, SpinnerColumn

from shared_console import console, CustomTimeElapsedColumn


# init(autoreset=True)


class StreamOutput:
    def __init__(self, agent):
        self.agent = agent
        # ANSI 颜色代码
        self.CYAN = "\033[96m"
        self.LIGHT_BLUE = "\033[38;5;123m"
        self.LIGHT_GRAY = "\033[38;2;140;140;140m"
        self.GREEN = "\033[92m"
        self.RESET = "\033[0m"
        self.WHITE = "\033[97m"

    async def stream_response(self, model_name, current_state, conversation_state):
        """处理 AI 流式响应"""
        current_response_text = ""  # 当前流式响应的文本
        current_reasoning_content = ""  # 推理内容
        need_point = True
        # need_point_think = True
        has_response = False

        with (Progress(
                SpinnerColumn(),  # 添加旋转动画
                TextColumn("[bold blue]{task.description}"),
                CustomTimeElapsedColumn(style="rgb(65,170,65)") ,
                console=console,
                transient=False
        ) as progress):
            task = progress.add_task(f"[cyan]Generating ...[/cyan]", total=None)
            async for message_chunk, metadata in self.agent.astream(
                    current_state, stream_mode="messages", config={"recursion_limit": 150}
            ):
                # 跳过 ToolMessage 类型
                if isinstance(message_chunk, ToolMessage):
                    continue

                # 处理 DeepSeek 推理内容
                if hasattr(message_chunk, 'additional_kwargs') and message_chunk.additional_kwargs:
                    reasoning_content = message_chunk.additional_kwargs.get('reasoning_content', '')
                    if reasoning_content:
                        current_reasoning_content += reasoning_content
                        print(f"{self.LIGHT_GRAY}{reasoning_content}{self.RESET}", end='')
                        has_response = True
                        continue

                # 处理 Gemini 推理内容
                if isinstance(message_chunk.content, list):
                    for content_item in message_chunk.content:
                        if isinstance(content_item, dict):
                            # Gemini 推理内容处理
                            if content_item.get('type') == 'thinking':
                                thinking_content = content_item.get('thinking', '')
                                if thinking_content:
                                    current_reasoning_content += thinking_content
                                    print(f"{self.LIGHT_GRAY}{thinking_content}{self.RESET}", end='')
                                    has_response = True
                                continue

                # 普通文本处理
                if message_chunk.content:
                    chunk_text = ''
                    if isinstance(message_chunk.content, list):
                        for content_item in message_chunk.content:
                            if isinstance(content_item, dict) and 'type' in content_item and content_item.get(
                                    'type') == 'text':
                                text_content = content_item.get('text', '')
                                chunk_text += text_content
                    elif isinstance(message_chunk.content, str):
                        text_content = message_chunk.content
                        chunk_text += text_content

                    if chunk_text != '':
                        if need_point and "qwen" in model_name:
                            print(f"{self.CYAN}\n● {self.RESET}", end='')
                            need_point = False
                        elif need_point:
                            print(f"{self.CYAN}\n● {self.RESET}", end='')
                            need_point = False

                        has_response = True
                        print(chunk_text, end="")

                        current_response_text += chunk_text

                if hasattr(message_chunk, 'response_metadata') and message_chunk.response_metadata:
                    if 'finish_reason' in message_chunk.response_metadata:
                        if has_response and 'qwen' in model_name:
                            print("\n", end='')
                        has_response = False
                        continue

            # 保存最终状态
            print("\n", flush=True)
            progress.stop_task(task)
            progress.update(task, description=f"[bold green]✓[/bold green] {self.CYAN}Completed{self.RESET}")

            additional_kwargs = {'reasoning_content': current_reasoning_content}
            ai_response = AIMessage(
                content=current_response_text,
                additional_kwargs=additional_kwargs)
            conversation_state["messages"].extend([ai_response])
            conversation_state["llm_calls"] += 1
