"""
QozeCode Skills Tools - LLM 可调用的技能管理工具
"""

from langchain_core.tools import tool
from skills.skill_manager import SkillManager
from shared_console import console
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
def activate_skill(skill_name: str) -> str:
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

        # 返回技能内容供 LLM 使用
        return f"[SKILL_ACTIVATED] 技能 '{skill_name}' 已成功激活！\n\n{skill.content}"

    except Exception as e:
        error_msg = f"[SKILL_ERROR] 激活技能时发生错误: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        return error_msg


@tool
def list_available_skills() -> str:
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
def deactivate_skill(skill_name: str) -> str:
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


@tool
def get_skill_install_guide(skill_name: str, skill_source: str = None) -> str:
    """
    获取技能安装指引。当需要安装新技能时，调用此工具获取详细的安装步骤和指引。
    
    此工具只返回安装指引，不执行实际安装。Agent 应该根据返回的指引自行执行安装操作。
    
    Args:
        skill_name: 要安装的技能名称
        skill_source: 技能来源（可选），可以是：
            - URL地址（以下载技能内容）
            - 技能内容的描述/说明
            - 如不提供，则生成通用技能模板

    Returns:
        详细的安装指引，包含：
        - 安装路径信息
        - 目录结构要求
        - SKILL.md 文件格式规范
        - 路径修复注意事项
        - 安装后的验证步骤
    """
    from pathlib import Path

    try:
        skill_manager = get_skill_manager()

        # 检查是否已存在
        if skill_name in skill_manager.skills:
            existing = skill_manager.skills[skill_name]
            return f"""[SKILL_EXISTS] 技能 '{skill_name}' 已存在！

📍 现有位置: {existing.location}
📝 描述: {existing.description}

如需重新安装，请先使用 deactivate_skill 停用后手动删除，然后重新获取安装指引。"""

        install_dir = f"~/.qoze/skills/{skill_name}"

        # 构建安装指引
        guide_lines = [
            f"[SKILL_INSTALL_GUIDE] 技能 '{skill_name}' 安装指引",
            "",
            "=" * 60,
            "📋 安装步骤",
            "=" * 60,
            "",
            f"步骤 1: 创建技能目录",
            f"  目标路径: {install_dir}",
            f"  命令: mkdir -p {install_dir}",
            "",
            f"步骤 2: 创建 SKILL.md 主文件",
            f"  文件路径: {install_dir}/SKILL.md",
            "",
            "=" * 60,
            "📝 SKILL.md 文件格式规范",
            "=" * 60,
            "",
            "SKILL.md 必须包含 YAML frontmatter 和 Markdown 内容：",
            "",
            "```markdown",
            "---",
            f"name: {skill_name}",
            "description: \"技能描述，简要说明此技能的作用\"",
            "version: 1.0.0",
            "author: optional",
            "---",
            "",
            "# 技能标题",
            "",
            "## 适用场景",
            "说明此技能适用于什么场景...",
            "",
            "## 工作流",
            "1. 第一步...",
            "2. 第二步...",
            "",
            "## 可用工具/命令",
            "- 工具1: 说明",
            "- 工具2: 说明",
            "",
            "## 最佳实践",
            "- 建议1",
            "- 建议2",
            "```",
            "",
            "=" * 60,
            "🔧 路径修复指南（重要）",
            "=" * 60,
            "",
            "在技能内容中，需要特别注意路径的写法：",
            "",
            "❌ 避免使用以下相对路径格式：",
            "  - .qoze/skills/{skill_name}/scripts/xxx.py",
            "  - ./scripts/xxx.py",
            "",
            "✅ 推荐使用以下方式之一：",
            f"  1. 用户目录: ~/.qoze/skills/{skill_name}/scripts/xxx.py",
            "",
            "如果技能内容中包含对其他技能的引用，例如：",
            f"  python .qoze/skills/other-skill/scripts/tool.py",
            "",
            "应该修改为：",
            f"  python ~/.qoze/skills/other-skill/scripts/tool.py",
            "",
        ]

        # 如果有技能来源，添加下载指引
        if skill_source:
            guide_lines.extend([
                "=" * 60,
                "📥 技能内容获取",
                "=" * 60,
                "",
                f"技能来源: {skill_source}",
                "",
            ])

            if skill_source.startswith(('http://', 'https://')):
                guide_lines.extend([
                    "来源类型: URL",
                    "建议操作:",
                    f"  1. 下载内容: curl -o /tmp/{skill_name}_skill.md '{skill_source}'",
                    f"  2. 检查内容: cat /tmp/{skill_name}_skill.md",
                    f"  3. 复制到目标位置并修复路径",
                    "",
                ])
            else:
                guide_lines.extend([
                    "来源类型: 描述/说明",
                    "建议操作:",
                    "  根据描述创建符合上述格式的 SKILL.md 文件",
                    "",
                ])

        # 添加可选的资源目录结构
        guide_lines.extend([
            "=" * 60,
            "📁 可选目录结构",
            "=" * 60,
            "",
            f"如果技能需要额外的脚本或资源，可以创建以下目录：",
            "",
            f"{install_dir}/",
            f"├── SKILL.md          # 主技能文件（必需）",
            f"├── scripts/          # 脚本文件（可选）",
            f"│   └── tool.py",
            f"├── templates/        # 模板文件（可选）",
            f"├── assets/           # 静态资源（可选）",
            f"├── examples/         # 示例（可选）",
            f"└── references/       # 参考资料（可选）",
            "",
            "=" * 60,
            "✅ 安装后验证步骤",
            "=" * 60,
            "",
            "1. 检查文件是否存在:",
            f"   cat {install_dir}/SKILL.md",
            "",
            "2. 刷新技能列表:",
            "   调用 list_available_skills() 查看新技能是否出现",
            "",
            "3. 激活技能测试:",
            f"   调用 activate_skill('{skill_name}') 验证是否能正常激活",
            "",
            "=" * 60,
        ])

        return "\n".join(guide_lines)

    except Exception as e:
        error_msg = f"[SKILL_ERROR] 获取安装指引时发生错误: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        return error_msg
