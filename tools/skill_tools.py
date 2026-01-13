#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode Skills Tools - LLM 可调用的技能管理工具
"""

from langchain_core.tools import tool
from typing import List, Optional
from utils.skill_manager import SkillManager
from shared_console import console
from rich.panel import Panel
from rich.table import Table

# 全局技能管理器实例
_skill_manager = None


def get_skill_manager() -> SkillManager:
    """获取全局技能管理器实例"""
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager


@tool
async def activate_skill(skill_name: str) -> str:
    """
    激活指定的技能以获得专业化能力。
    
    技能是针对特定任务的专业指导包，包含详细的步骤、最佳实践和资源。
    当你需要处理特定领域的任务时，应该激活相关技能。
    
    Args:
        skill_name: 要激活的技能名称
        
    Returns:
        激活结果和技能内容
    """
    try:
        skill_manager = get_skill_manager()

        # 检查技能是否存在
        if skill_name not in skill_manager.skills:
            available_skills = list(skill_manager.get_available_skills().keys())
            return f"[SKILL_NOT_FOUND] 技能 '{skill_name}' 不存在。\n可用技能: {', '.join(available_skills)}"

        # 激活技能
        skill = skill_manager.activate_skill(skill_name)
        if not skill:
            return f"[SKILL_ACTIVATION_FAILED] 无法激活技能 '{skill_name}'"

        # # 显示激活信息
        # panel = Panel(
        #     f"🎯 **技能已激活**: {skill.name}\n\n"
        #     f"📖 **描述**: {skill.description}\n\n"
        #     f"📁 **层级**: {skill.tier}\n\n"
        #     f"📂 **资源**: {len(skill.resources)} 个关联资源",
        #     title="[green]Skill Activated[/green]",
        #     border_style="green"
        # )
        # console.print(panel)
        #
        # 返回技能内容供 LLM 使用
        return f"[SKILL_ACTIVATED] 技能 '{skill_name}' 已成功激活！\n\n{skill.content}"

    except Exception as e:
        error_msg = f"[SKILL_ERROR] 激活技能时发生错误: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        return error_msg


@tool
async def list_available_skills() -> str:
    """
    列出所有可用的技能及其描述。
    
    使用此工具来了解当前环境中有哪些技能可以激活。
    
    Returns:
        可用技能的列表和描述
    """
    try:
        skill_manager = get_skill_manager()
        available_skills = skill_manager.get_available_skills()

        if not available_skills:
            return "[NO_SKILLS] 当前没有可用的技能"

        # 创建技能列表
        skills_info = ["可用技能列表:"]
        for name, description in available_skills.items():
            skills_info.append(f"• **{name}**: {description}")

        result = "\n".join(skills_info)

        # 同时显示在控制台
        table = Table(title="Available Skills")
        table.add_column("Skill Name", style="cyan", no_wrap=True)
        table.add_column("Description", style="white")

        for name, description in available_skills.items():
            table.add_row(name, description)

        console.print(table)

        return result

    except Exception as e:
        error_msg = f"[SKILL_ERROR] 获取技能列表时发生错误: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        return error_msg


@tool
async def deactivate_skill(skill_name: str) -> str:
    """
    停用指定的技能。
    
    当不再需要某个技能的专业化指导时，可以停用它以释放上下文空间。
    
    Args:
        skill_name: 要停用的技能名称
        
    Returns:
        停用结果
    """
    try:
        skill_manager = get_skill_manager()

        if skill_name not in skill_manager.active_skills:
            return f"[SKILL_NOT_ACTIVE] 技能 '{skill_name}' 当前未激活"

        skill_manager.deactivate_skill(skill_name)

        console.print(f"[yellow]🔻 技能 '{skill_name}' 已停用[/yellow]")
        return f"[SKILL_DEACTIVATED] 技能 '{skill_name}' 已成功停用"

    except Exception as e:
        error_msg = f"[SKILL_ERROR] 停用技能时发生错误: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        return error_msg
