#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
输入处理模块 - 负责用户输入的处理和特殊命令执行
"""

import sys
from langchain_core.messages import HumanMessage

from shared_console import console
from utils.command_exec import run_command


class InputProcessor:
    def __init__(self, input_manager):
        self.input_manager = input_manager

    async def get_user_input(self, plan_mode: bool):
        """获取并处理用户输入"""
        try:
            # 显示提示信息
            console.print("\n")
            console.print("[bold cyan]您：[bold cyan]")
            # 根据 plane_mode 显示不同的提示信息
            if plan_mode:
                console.print(f"[dim]💡 计划模式 - 回车执行请求（输入 'line' 进入多行编辑）[/dim]")
            else:
                console.print(f"[dim]💡 回车执行请求（输入 'line' 进入多行编辑）[/dim]")

            # 首先使用单行输入
            user_input = input().strip()

            # 如果用户输入 'line'，则切换到多行编辑模式
            if user_input.lower() == 'line':
                console.print("[dim]💡 已进入多行编辑模式，输入内容后按 [Ctrl+D] 提交[/dim]")
                user_input = await self.input_manager.get_user_input()

            # 处理空输入
            if not user_input:
                console.print("💡 请输入您的问题或指令", style="dim")
                return ""

            # 处理特殊命令
            return await self._handle_special_commands(user_input)

        except (UnicodeDecodeError, UnicodeError, KeyboardInterrupt) as e:
            if isinstance(e, KeyboardInterrupt):
                raise e
            return ""

    async def _handle_special_commands(self, user_input):
        """处理特殊命令"""
        # # 处理 clear 命令
        # if user_input.lower() == 'clear':
        #     console.clear()
        #     return ""

        # 处理 ! 命令
        if user_input.startswith('!') or user_input.startswith('！'):
            command = user_input.lstrip('!！').strip()
            if not command:
                console.print("⚠️ 请输入要执行的命令，如: ! ls -la", style="yellow")
                return ""

            # 执行命令
            output = run_command(command)

            # 创建用户消息
            # combined_content = f"command:{command}\n\nresult:{output}"
            # if session_id in self.local_sessions:
            #     self.local_sessions[session_id]["messages"].extend([
            #         HumanMessage(content=combined_content)
            #     ])
            return ""

        # 在有效输入后添加视觉分隔
        console.print()
        return user_input
