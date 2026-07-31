"""
QozeCode Skills Tools - LLM 可调用的技能管理工具
"""

from langchain_core.tools import tool
from skills.skill_manager import SkillManager
from shared_console import console
from config_manager import _get_qoze_base_dir
import os
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
        skill_manager.refresh_skills()  # 重新扫描技能目录，确保新安装技能可激活

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
        skill_manager.refresh_skills()  # 重新扫描技能目录，确保新安装技能可见
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
    只要当要求安装skill的时候，才调用这个工具，调用此工具获取详细的安装步骤和指引。
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

现有位置: {existing.location}
描述: {existing.description}

如需重新安装，请先使用 deactivate_skill 停用后手动删除，然后重新获取安装指引。"""

        install_dir = os.path.join(_get_qoze_base_dir(), "skills", skill_name)

        # 构建安装指引
        guide_lines = [
            f"[SKILL_INSTALL_GUIDE] 技能 '{skill_name}' 安装指引",
            "",
            "=" * 60,
            "安装位置（默认用户级公共目录）",
            "=" * 60,
            "",
            "QozeCode 按以下优先级发现技能（目录内含 SKILL.md 即视为一个技能）：",
            "  1. 项目级: .qoze/skills/                     —— 随仓库分发，仅当前项目可见",
            f"  2. 用户级: {_get_qoze_base_dir()}/skills/   —— 本机所有项目共享（默认）",
            "  3. 内置:   项目根 .qoze/skills/",
            "",
            "约定：用户未明确指定层级时，一律安装到用户级目录：",
            f"  目标目录: {install_dir}",
            f"  创建命令: mkdir -p {install_dir}",
            "",
            "仅当用户明确要求「随项目/仓库分发」时，才安装到项目级：",
            f"  .qoze/skills/{skill_name}/",
            "",
            "=" * 60,
            "SKILL.md 文件格式规范",
            "=" * 60,
            "",
            "SKILL.md 必须以 '---' 开头（YAML frontmatter），name 与 description 必填：",
            "",
            "```markdown",
            "---",
            f"name: {skill_name}",
            'description: "技能描述，简要说明此技能的作用"',
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
            "- name 必填，且建议与目录名一致（SkillManager 按 frontmatter 的 name 注册技能）",
            "- 主文件必须命名为 SKILL.md（区分大小写）",
            "",
            "=" * 60,
            "路径适配指南（重要：QozeCode 特有，必读）",
            "=" * 60,
            "",
            "1) Agent 执行命令时 cwd 是项目根目录，而不是技能目录。",
            "   SKILL.md 中所有相对路径（scripts/xxx.py、./xxx.py、skills/xxx/...）",
            "   执行时都会失败，必须改为基于技能实际安装目录的绝对路径。",
            "",
            "2) 默认绝对路径前缀（用户级安装）：",
            f"   {install_dir}/",
            "   示例：把 `python scripts/tool.py` 改为",
            f"   `python {install_dir}/scripts/tool.py`",
            "",
            "3) 技能内文档相对链接（references/xxx.md、../other-skill/SKILL.md）：",
            f"   读取时同样要用绝对路径，如 {install_dir}/references/xxx.md；",
            "   多技能互相引用（如 ../lark-shared/SKILL.md）要求相关技能安装在",
            "   同一级 skills/ 目录下且目录名保持不变，不要改动目录层级。",
            "",
            "4) 建议在 SKILL.md 顶部添加「路径基准」说明块，便于 Agent 定位：",
            f"   > 本技能安装于 {install_dir}/，所有相对引用均以此目录为基准",
            "   > 转为绝对路径后再执行。",
            "",
            "5) 若实际安装到项目级 .qoze/skills/，绝对路径前缀为",
            f"   {os.path.abspath('.qoze/skills')}/{skill_name}/；",
            "   路径修复时必须与技能实际所在层级保持一致。",
            "",
        ]

        # 如果有技能来源，添加下载指引
        if skill_source:
            guide_lines.extend([
                "=" * 60,
                "技能内容获取（多文件技能）",
                "=" * 60,
                "",
                f"技能来源: {skill_source}",
                "",
            ])

            if skill_source.startswith(('http://', 'https://')):
                guide_lines.extend([
                    "来源类型: URL",
                    "",
                    "【GitHub 仓库内的技能目录】（推荐，可完整保留 SKILL.md + references/ + scripts/）：",
                    f"  git clone --depth 1 --filter=blob:none --sparse <repo_url> .qoze/{skill_name}-install",
                    f"  git -C .qoze/{skill_name}-install sparse-checkout set --no-cone <技能在仓库内的路径>",
                    f"  cp -R .qoze/{skill_name}-install/<技能在仓库内的路径> {install_dir}",
                    f"  rm -rf .qoze/{skill_name}-install",
                    "",
                    "【单个文件 URL】：",
                    f"  curl -fsSL '<url>' -o {install_dir}/SKILL.md",
                    "",
                    "下载/复制完成后，必须按上方「路径适配指南」修正所有相对路径引用。",
                    "",
                ])
            else:
                guide_lines.extend([
                    "来源类型: 描述/说明",
                    "建议操作:",
                    "  根据描述创建符合上述格式的 SKILL.md 文件（含 name/description frontmatter）",
                    "  如描述中涉及脚本/资源，按「路径适配指南」使用绝对路径",
                    "",
                ])

        # 添加可选的资源目录结构
        guide_lines.extend([
            "=" * 60,
            "可选目录结构",
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
            "安装后验证步骤",
            "=" * 60,
            "",
            "1. 检查文件是否存在且 frontmatter 完整:",
            f"   cat {install_dir}/SKILL.md",
            "   （确认以 '---' 开头，且含 name/description）",
            "",
            "2. 刷新技能列表（list_available_skills 会自动重新扫描技能目录）:",
            "   调用 list_available_skills() 查看新技能是否出现",
            "",
            "3. 激活技能测试:",
            f"   调用 activate_skill('{skill_name}') 验证能否正常加载内容",
            "",
            "4. 如技能包含脚本/资源，检查绝对路径引用与可执行权限。",
            "",
            "=" * 60,
        ])

        return "\n".join(guide_lines)

    except Exception as e:
        error_msg = f"[SKILL_ERROR] 获取安装指引时发生错误: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        return error_msg
