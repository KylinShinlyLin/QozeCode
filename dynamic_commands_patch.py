#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态技能命令生成器
为 QozeCode TUI 提供基于当前技能状态的动态命令补全
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills_tui_integration import SkillsTUIHandler
from typing import List, Tuple


class DynamicCommandsGenerator:
    """动态命令生成器，基于技能系统状态"""

    def __init__(self):
        self.base_commands = [
            ("/clear", "清理会话上下文"),
            ("/line", "进入多行编辑模式"),
            ("/qoze init", "初始化项目指引"),
            ("/skills", "显示技能系统帮助"),
            ("/skills list", "列出所有可用技能"),
            ("/skills status", "显示技能系统状态"),
            ("/quit", "退出程序"),
        ]

    def get_dynamic_commands(self) -> List[Tuple[str, str]]:
        """获取包含动态技能命令的完整命令列表"""
        commands = self.base_commands.copy()

        try:
            # 每次都创建新的 handler 实例以确保获取最新状态
            skills_handler = SkillsTUIHandler()
            skills_handler.skill_manager.refresh_skills()

            # 获取所有技能和激活状态
            all_skills = getattr(skills_handler.skill_manager, 'skills', {})
            active_skills = getattr(skills_handler.skill_manager, 'active_skills', [])

            # 为每个可用技能添加 enable/disable 命令
            for skill_name in all_skills:
                if skill_name in active_skills:
                    # 技能已激活，提供禁用选项
                    commands.append((
                        f"/skills disable {skill_name}",
                        f"(当前已激活 ✅)"
                    ))
                else:
                    # 技能未激活，提供启用选项
                    commands.append((
                        f"/skills enable {skill_name}",
                        f"(当前未激活 ⭕)"
                    ))

        except Exception as e:
            # 如果获取技能状态失败，至少提供通用的 enable/disable 命令
            commands.extend([
                ("/skills enable", "启用指定技能"),
                ("/skills disable", "禁用指定技能"),
            ])

        return commands

    def get_skills_commands(self, search_term: str) -> List[Tuple[str, str]]:
        """获取技能相关的命令列表（用于 skills 开头的输入）"""
        base_skills_commands = [
            ("skills", "显示技能系统帮助"),
            ("skills list", "列出所有可用技能"),
            ("skills list active", "列出启用的技能"),
            ("skills status", "显示技能系统状态"),
            ("skills refresh", "刷新技能缓存"),
            ("skills create", "创建新技能"),
            ("skills help", "显示技能命令帮助"),
        ]

        try:
            # 每次都创建新的 handler 实例以确保获取最新状态
            skills_handler = SkillsTUIHandler()
            skills_handler.skill_manager.refresh_skills()

            # 获取所有技能和激活状态
            all_skills = getattr(skills_handler.skill_manager, 'skills', {})
            active_skills = getattr(skills_handler.skill_manager, 'active_skills', [])

            # 添加具体的技能操作命令
            for skill_name in all_skills:
                skill_info = all_skills[skill_name]
                skill_desc = getattr(skill_info, 'description', f'{skill_name} 技能')

                if skill_name in active_skills:
                    base_skills_commands.append((
                        f"skills disable {skill_name}",
                        f"禁用 {skill_desc} (当前已激活 ✅)"
                    ))
                else:
                    base_skills_commands.append((
                        f"skills enable {skill_name}",
                        f"启用 {skill_desc} (当前未激活 ⭕)"
                    ))

        except Exception as e:
            # 如果获取失败，添加通用命令
            base_skills_commands.extend([
                ("skills enable <name>", "启用指定技能"),
                ("skills disable <name>", "禁用指定技能"),
            ])

        return base_skills_commands


def get_dynamic_commands():
    """供外部调用的函数"""
    generator = DynamicCommandsGenerator()
    return generator.get_dynamic_commands()


def get_skills_commands(search_term=""):
    """供外部调用的函数 - 获取技能相关命令"""
    generator = DynamicCommandsGenerator()
    return generator.get_skills_commands(search_term)


if __name__ == "__main__":
    # 测试功能
    print("=== 动态命令测试 ===")
    commands = get_dynamic_commands()
    for cmd, desc in commands:
        if 'skills' in cmd:
            print(f"{cmd:<30} | {desc}")

    print("\n=== Skills 命令测试 ===")
    skills_commands = get_skills_commands("skills")
    for cmd, desc in skills_commands:
        if 'enable' in cmd or 'disable' in cmd:
            print(f"{cmd:<30} | {desc}")
