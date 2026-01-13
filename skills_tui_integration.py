"""
QozeCode Skills TUI 集成模块
为主 TUI 提供 skills 命令支持 - 简化版本
"""

from utils.skill_manager import SkillManager


class SkillsTUIHandler:
    """Skills 命令的 TUI 处理器 - 简化版本"""

    def __init__(self):
        self.skill_manager = SkillManager()

    def handle_skills_command(self, command_parts: list) -> tuple[bool, str]:
        """
        处理 skills 相关命令

        Args:
            command_parts: 分割后的命令部分，如 ['skills', 'list']

        Returns:
            tuple[bool, str]: (是否成功处理, 输出消息)
        """
        if len(command_parts) == 1:
            # 只输入 "skills"，显示帮助
            return True, self._get_skills_help()

        subcommand = command_parts[1].lower()

        if subcommand == "list":
            return self._handle_list(command_parts[2:])
        elif subcommand == "status":
            return self._handle_status()
        elif subcommand == "enable":
            return self._handle_enable(command_parts[2:])
        elif subcommand == "disable":
            return self._handle_disable(command_parts[2:])
        else:
            return False, f"未知的 skills 子命令: {subcommand}\n使用 'skills help' 查看可用命令"

    def _handle_list(self, args: list) -> tuple[bool, str]:
        """处理 list 命令"""
        try:
            # 刷新技能列表
            self.skill_manager.refresh_skills()

            if not hasattr(self.skill_manager, 'skills') or not self.skill_manager.skills:
                return True, "📝 当前没有发现任何技能\n\n使用 'skills create' 创建新技能"

            # 检查是否只显示激活的技能
            only_active = len(args) > 0 and args[0].lower() == "active"

            # 构建简单的文本输出
            output_lines = []
            if only_active:
                output_lines.append("🎯 已激活的技能:")
            else:
                output_lines.append("📚 所有可用技能:")

            output_lines.append("-" * 50)

            count = 0
            for name, skill in self.skill_manager.skills.items():
                if only_active and name not in self.skill_manager.active_skills:
                    continue

                is_active = name in self.skill_manager.active_skills
                status = "✅ 已激活" if is_active else "⭕ 未激活"
                location_type = "📁 项目" if ".qoze/skills" in skill.location else "👤 用户"

                output_lines.append(f"{name}")
                output_lines.append(f"  状态: {status}")
                output_lines.append(f"  描述: {skill.description}")
                output_lines.append(f"  位置: {location_type}")
                output_lines.append("")
                count += 1

            if only_active and count == 0:
                output_lines.append("当前没有已激活的技能")
            elif count == 0:
                output_lines.append("没有找到技能")
            else:
                output_lines.append(f"共 {count} 个技能")

            return True, "\n".join(output_lines)

        except Exception as e:
            return False, f"列出技能失败: {str(e)}"

    def _handle_status(self) -> tuple[bool, str]:
        """处理 status 命令"""
        try:
            self.skill_manager.refresh_skills()

            total_count = len(self.skill_manager.skills) if hasattr(self.skill_manager, 'skills') else 0
            active_count = len(self.skill_manager.active_skills) if hasattr(self.skill_manager, 'active_skills') else 0

            output_lines = [
                "🔧 Skills 系统状态",
                "-" * 30,
                f"总技能数: {total_count}",
                f"已激活: {active_count}",
                f"未激活: {total_count - active_count}",
                "",
                "技能目录:",
                f"  项目级: .qoze/skills/",
                f"  用户级: ~/.qoze/skills/",
            ]

            return True, "\n".join(output_lines)

        except Exception as e:
            return False, f"获取状态失败: {str(e)}"

    def _handle_enable(self, args: list) -> tuple[bool, str]:
        """处理 enable 命令"""
        if not args:
            return False, "请指定要启用的技能名称\n示例: skills enable python-code-review"

        skill_name = args[0]
        try:
            skill = self.skill_manager.activate_skill(skill_name)
            if skill:
                return True, f"[dim bold green] ✓ 已激活技能: {skill_name}[/]"
            else:
                return False, f"[dim bold red] ✗ 激活技能失败: {skill_name}[/]"
        except Exception as e:
            return False, f"❌ 启用技能失败: {skill_name} - {str(e)}"
            return False, f"启用技能失败: {str(e)}"

    def _handle_disable(self, args: list) -> tuple[bool, str]:
        """处理 disable 命令"""
        if not args:
            return False, "请指定要禁用的技能名称\n示例: skills disable python-code-review"

        skill_name = args[0]
        try:
            self.skill_manager.deactivate_skill(skill_name)
            return True, f"[dim bold red] 已停用技能: {skill_name} [/]"
        except Exception as e:
            return False, f"❌ 禁用技能失败: {skill_name} - {str(e)}"
            return False, f"禁用技能失败: {str(e)}"

    # def _handle_refresh(self) -> tuple[bool, str]:
    #     """处理 refresh 命令"""
    #     try:
    #         self.skill_manager.refresh_skills()
    #         count = len(self.skill_manager.skills) if hasattr(self.skill_manager, 'skills') else 0
    #         return True, f"🔄 已刷新技能列表，发现 {count} 个技能"
    #     except Exception as e:
    #         return False, f"刷新技能失败: {str(e)}"

    # def _handle_create(self) -> tuple[bool, str]:
    #     """处理 create 命令"""
    #     return True, (
    #         "📝 创建新技能:\n\n"
    #         "1. 在 .qoze/skills/ 下创建新目录\n"
    #         "2. 在目录中创建 SKILL.md 文件\n"
    #         "3. 按以下格式编写:\n\n"
    #         "---\n"
    #         "name: my-skill\n"
    #         "description: 技能描述\n"
    #         "---\n\n"
    #         "# 技能内容\n"
    #         "详细的指导步骤...\n\n"
    #     )

#     def _get_skills_help(self) -> str:
#         """获取帮助信息"""
#         return """🎯 QozeCode Skills 系统帮助
#
# 可用命令:
#   skills list              - 列出所有可用技能
#   skills list active       - 列出已激活的技能
#   skills status            - 显示系统状态
#   skills enable <name>     - 启用指定技能
#   skills disable <name>    - 禁用指定技能
#   skills refresh           - 刷新技能列表
#   skills create           - 显示创建技能的说明
#   skills help             - 显示此帮助
#
# 示例:
#   skills list
#   skills enable python-code-review
#   skills status
#
# 技能会根据任务需求由 AI 自动激活，也可手动管理。
# """
