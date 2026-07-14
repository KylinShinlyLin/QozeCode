#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode Skills Management System
基于 gemini-cli 的设计理念，实现 Agent Skills 管理
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re
from shared_console import console
from rich.panel import Panel
from rich.table import Table


@dataclass
class Skill:
    """技能数据类"""
    name: str
    description: str
    content: str
    location: str
    tier: str  # 'project', 'user', 'builtin'
    resources: List[str]  # 关联的资源文件/目录
    enabled: bool = True


class SkillManager:
    """技能管理器：发现、加载、管理技能"""

    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.skills: Dict[str, Skill] = {}
        self.active_skills: List[str] = []
        self.disabled_skills: List[str] = []

        # 技能发现路径（按优先级）
        self.skill_paths = self._get_skill_paths()
        self.config_file = Path.home() / ".qoze" / "skills_config.json"

        self._load_config()
        self._discover_skills()

    def _get_skill_paths(self) -> List[Tuple[str, str]]:
        """获取技能搜索路径，返回 (路径, 层级) 元组"""
        paths = []

        # 1. 项目级技能 (最高优先级)
        project_skills = Path(".qoze/skills")
        if project_skills.exists():
            paths.append((str(project_skills), "project"))

        # 2. 用户级技能
        user_skills = Path.home() / ".qoze" / "skills"
        user_skills.mkdir(parents=True, exist_ok=True)
        paths.append((str(user_skills), "user"))

        # 3. 内置技能
        builtin_skills = Path(__file__).parent.parent / ".qoze" / "skills"
        if builtin_skills.exists():
            paths.append((str(builtin_skills), "builtin"))

        return paths

    def _load_config(self):
        """加载技能配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.disabled_skills = config.get('disabled_skills', [])
                    self.active_skills = config.get('active_skills', [])
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load skills config: {e}[/yellow]")

    def _save_config(self):
        """保存技能配置"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            config = {
                'disabled_skills': self.disabled_skills,
                'active_skills': self.active_skills
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            console.print(f"[red]Error saving skills config: {e}[/red]")

    def _discover_skills(self):
        """发现所有可用技能"""
        self.skills.clear()

        for skill_path, tier in self.skill_paths:
            if not os.path.exists(skill_path):
                continue

            for item in os.listdir(skill_path):
                skill_dir = Path(skill_path) / item
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skill = self._load_skill(str(skill_file), tier)
                        if skill and skill.name not in self.skills:
                            self.skills[skill.name] = skill

    def _load_skill(self, skill_file_path: str, tier: str) -> Optional[Skill]:
        """加载单个技能文件"""
        try:
            with open(skill_file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析 frontmatter
            if content.startswith('---\n'):
                parts = content.split('---\n', 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    skill_content = parts[2].strip()
                else:
                    return None
            else:
                return None

            # 获取技能基本信息
            name = frontmatter.get('name')
            description = frontmatter.get('description', '')

            if not name:
                console.print(f"[yellow]Warning: Skill {skill_file_path} missing name[/yellow]")
                return None

            # 扫描关联资源
            skill_dir = Path(skill_file_path).parent
            resources = self._scan_skill_resources(skill_dir)

            return Skill(
                name=name,
                description=description,
                content=skill_content,
                location=skill_file_path,
                tier=tier,
                resources=resources,
                enabled=name not in self.disabled_skills
            )

        except Exception as e:
            console.print(f"[red]Error loading skill {skill_file_path}: {e}[/red]")
            return None

    def _scan_skill_resources(self, skill_dir: Path) -> List[str]:
        """扫描技能相关资源"""
        resources = []

        # 常见的资源目录
        resource_dirs = ['scripts', 'templates', 'assets', 'references', 'examples']

        for dir_name in resource_dirs:
            resource_path = skill_dir / dir_name
            if resource_path.exists() and resource_path.is_dir():
                resources.append(str(resource_path))

        # 扫描根目录下的其他文件
        for item in skill_dir.iterdir():
            if item.name != "SKILL.md" and item.is_file():
                resources.append(str(item))

        return resources

    def get_available_skills(self) -> Dict[str, str]:
        """获取可用技能的名称和描述（用于 LLM 发现）"""
        available = {}
        for name, skill in self.skills.items():
            if skill.enabled:
                available[name] = skill.description
        return available

    def activate_skill(self, skill_name: str) -> Optional[Skill]:
        """激活指定技能"""
        if skill_name not in self.skills:
            return None

        skill = self.skills[skill_name]
        if not skill.enabled:
            console.print(f"[yellow]Skill '{skill_name}' is disabled[/yellow]")
            return None

        if skill_name not in self.active_skills:
            self.active_skills.append(skill_name)
            self._save_config()

        return skill

    def deactivate_skill(self, skill_name: str):
        """停用指定技能"""
        if skill_name in self.active_skills:
            self.active_skills.remove(skill_name)
            self._save_config()

    def disable_skill(self, skill_name: str):
        """禁用技能"""
        if skill_name not in self.disabled_skills:
            self.disabled_skills.append(skill_name)
            if skill_name in self.skills:
                self.skills[skill_name].enabled = False
            self._save_config()

    def enable_skill(self, skill_name: str):
        """启用技能"""
        if skill_name in self.disabled_skills:
            self.disabled_skills.remove(skill_name)
            if skill_name in self.skills:
                self.skills[skill_name].enabled = True
            self._save_config()

    def get_active_skills_content(self) -> str:
        """获取所有激活技能的摘要（用于注入 LLM 上下文）

        只返回技能名称和描述，不返回完整 SKILL.md 内容。
        完整内容通过 activate_skill 工具按需注入。
        """
        if not self.active_skills:
            return ""

        lines = [f"共 {len(self.active_skills)} 个激活技能："]
        for skill_name in self.active_skills:
            if skill_name in self.skills:
                skill = self.skills[skill_name]
                lines.append(f"- **{skill.name}**: {skill.description}")
        return "\n".join(lines)

    def list_skills(self, show_all: bool = False):
        """列出技能"""
        table = Table(title="QozeCode Skills")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Tier", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Description", style="white")

        for name, skill in self.skills.items():
            if not show_all and not skill.enabled:
                continue

            status = "🟢 Active" if name in self.active_skills else \
                "🔴 Disabled" if not skill.enabled else \
                    "⚪ Available"

            table.add_row(name, skill.tier, status,
                          skill.description[:60] + "..." if len(skill.description) > 60 else skill.description)

        console.print(table)

    def refresh_skills(self):
        """刷新技能列表"""
        self._discover_skills()
