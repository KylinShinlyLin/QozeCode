#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode Skills CLI Commands
提供完整的技能管理命令行接口
"""

import argparse
import sys
import os
from pathlib import Path
from utils.skill_manager import SkillManager
from shared_console import console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

def create_skill_template():
    """创建技能模板"""
    console.print("[cyan]🎯 创建新技能模板[/cyan]")
    
    # 获取技能信息
    skill_name = Prompt.ask("技能名称 (例: python-web-scraper)")
    skill_description = Prompt.ask("技能描述 (简短描述何时使用此技能)")
    
    # 选择存放位置
    location_choice = Prompt.ask(
        "存放位置", 
        choices=["project", "user"], 
        default="user"
    )
    
    # 确定目录
    if location_choice == "project":
        skills_dir = Path(".qoze/skills")
        skills_dir.mkdir(parents=True, exist_ok=True)
    else:
        skills_dir = Path.home() / ".qoze" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建技能目录
    skill_dir = skills_dir / skill_name
    if skill_dir.exists():
        console.print(f"[red]❌ 技能目录已存在: {skill_dir}[/red]")
        return False
    
    skill_dir.mkdir(parents=True)
    
    # 创建 SKILL.md 文件
    skill_content = f"""---
name: {skill_name}
description: {skill_description}
---

# {skill_name.replace('-', ' ').title()}

## 📋 概述
{skill_description}

## 🎯 使用场景
描述何时应该使用此技能...

## 📖 详细指导

### 第一步：准备工作
- 列出需要的准备工作
- 检查前提条件

### 第二步：具体执行
- 详细的执行步骤
- 最佳实践建议
- 常见陷阱避免

### 第三步：验证和优化
- 如何验证结果
- 优化建议

## 🔧 相关工具和命令
```bash
# 常用命令示例
echo "在这里添加相关的命令示例"
```

## 📚 参考资源
- 相关文档链接
- 最佳实践文章
- 工具官方文档

## ⚠️ 注意事项
- 重要的注意事项
- 安全考虑
- 性能建议
"""
    
    skill_file = skill_dir / "SKILL.md"
    with open(skill_file, 'w', encoding='utf-8') as f:
        f.write(skill_content)
    
    # 创建常见资源目录
    (skill_dir / "scripts").mkdir(exist_ok=True)
    (skill_dir / "templates").mkdir(exist_ok=True)
    (skill_dir / "examples").mkdir(exist_ok=True)
    
    console.print(Panel(
        f"✅ 技能模板已创建!\n\n"
        f"📁 位置: {skill_dir}\n"
        f"📝 编辑: {skill_file}\n\n"
        f"你可以编辑 SKILL.md 文件来完善技能内容。",
        title="[green]Skill Created[/green]",
        border_style="green"
    ))
    
    return True

def main():
    """技能管理主入口"""
    parser = argparse.ArgumentParser(description="QozeCode Skills Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # list 命令
    list_parser = subparsers.add_parser("list", help="列出技能")
    list_parser.add_argument("--all", action="store_true", help="显示所有技能（包括禁用的）")
    
    # create 命令
    create_parser = subparsers.add_parser("create", help="创建新技能")
    
    # enable 命令
    enable_parser = subparsers.add_parser("enable", help="启用技能")
    enable_parser.add_argument("skill_name", help="技能名称")
    
    # disable 命令
    disable_parser = subparsers.add_parser("disable", help="禁用技能")
    disable_parser.add_argument("skill_name", help="技能名称")
    
    # refresh 命令
    refresh_parser = subparsers.add_parser("refresh", help="刷新技能列表")
    
    # status 命令
    status_parser = subparsers.add_parser("status", help="显示技能状态")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 初始化技能管理器
    skill_manager = SkillManager()
    
    if args.command == "list":
        skill_manager.list_skills(show_all=args.all)
    
    elif args.command == "create":
        create_skill_template()
    
    elif args.command == "enable":
        skill_manager.enable_skill(args.skill_name)
        console.print(f"[green]✅ 技能 '{args.skill_name}' 已启用[/green]")
    
    elif args.command == "disable":
        skill_manager.disable_skill(args.skill_name)
        console.print(f"[yellow]⚠️ 技能 '{args.skill_name}' 已禁用[/yellow]")
    
    elif args.command == "refresh":
        skill_manager.refresh_skills()
    
    elif args.command == "status":
        available = skill_manager.get_available_skills()
        active = skill_manager.active_skills
        disabled = skill_manager.disabled_skills
        
        console.print(Panel(
            f"📊 **技能状态统计**\n\n"
            f"• 可用技能: {len(available)}\n"
            f"• 激活技能: {len(active)}\n"
            f"• 禁用技能: {len(disabled)}\n\n"
            f"激活的技能: {', '.join(active) if active else '无'}\n"
            f"禁用的技能: {', '.join(disabled) if disabled else '无'}",
            title="[blue]Skills Status[/blue]",
            border_style="blue"
        ))

if __name__ == "__main__":
    main()

