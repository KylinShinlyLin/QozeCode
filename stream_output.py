#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流式输出模块 - 负责 AI 响应的流式输出和状态管理
"""

import sys
from langchain_core.messages import AIMessage, ToolMessage

from shared_console import console


class StreamOutput:
    def __init__(self, agent, local_sessions):
        self.agent = agent
        self.local_sessions = local_sessions

    async def stream_response(self, current_state, conversation_state):
        """处理 AI 流式响应"""
        current_response_text = ""  # 当前流式响应的文本
        need_point = True
        has_response = False

        CYAN = "\033[96m"
        RESET = "\033[0m"

        async for message_chunk, metadata in self.agent.astream(
                current_state, stream_mode="messages", config={"recursion_limit": 150}
        ):
            # 跳过 ToolMessage 类型
            if isinstance(message_chunk, ToolMessage):
                continue

            if message_chunk.content:
                # 提取文本内容
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
                    has_response = True
                    print(f"{CYAN}●{RESET} {chunk_text}" if need_point else chunk_text, end='', file=sys.stderr)
                    need_point = False
                    current_response_text += chunk_text

            if hasattr(message_chunk, 'response_metadata') and message_chunk.response_metadata:
                if 'finish_reason' in message_chunk.response_metadata:
                    if has_response:
                        print("\n", end='')
                    has_response = False
                    continue

        # 保存最终状态
        ai_response = AIMessage(content=current_response_text)
        conversation_state["messages"].extend([ai_response])
        conversation_state["llm_calls"] += 1
        # if session_id in self.local_sessions:
        #     self.local_sessions[session_id]["messages"].extend([
        #         current_state["messages"][-1], ai_response
        #     ])
        #     self.local_sessions[session_id]["llm_calls"] += 1
