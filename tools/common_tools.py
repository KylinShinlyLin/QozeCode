from langchain_core.tools import tool
from rich.markdown import Markdown
from rich.panel import Panel

# 导入共享的 console 实例
from shared_console import console


@tool
def ask(content: str) -> str:
    """Call this tool when the agent encounters situations requiring user intervention, pausing execution and waiting for user input.

    Use cases:
    - User authorization required
    - Need more information from user
    - User login required
    - User confirmation needed
    - Manual decision making required

    Args:
        content: The complete message content to display to the user, including the reason and required action

    Returns:
        Returns a message indicating the task has been paused, causing the agent to stop current task execution
    """

    try:
        ask_panel = Panel(
            Markdown(content, style="green"),
            subtitle="[bold blue]Qoze 回复[/bold blue]",
            border_style="blue",
            padding=(0, 2)
        )
        console.print(ask_panel)

        # 返回暂停消息，这将导致 agent 停止当前任务
        return f"AGENT_PAUSED: {content}"

    except Exception as e:
        error_msg = f"❌ ask 工具执行出错: {str(e)}"
        error_panel = Panel(
            Markdown(f"**消息**: {content}\n\n❌ **工具执行失败**\n\n🔍 **错误详情**: {str(e)}", style="green"),
            title="[bold green]Qoze 回复[/bold green]",
            border_style="green",
            padding=(0, 2)
        )
        console.print(error_panel)
        return error_msg

# @tool
# def confirm(question: str, default_yes: bool = False) -> str:
#     """Ask user for confirmation, suitable for scenarios requiring yes/no decisions.
#
#     Args:
#         question: The confirmation question to ask the user
#         default_yes: Whether the default answer is yes (default: False)
#
#     Returns:
#         Returns a message indicating user confirmation is needed, causing the agent to stop current task execution
#     """
#
#     default_text = "是" if default_yes else "否"
#
#     confirm_panel = Panel(
#         f"❓ [bold bright_yellow]{question}[/bold bright_yellow]\n\n"
#         f"💡 默认选择: [cyan]{default_text}[/cyan]\n"
#         f"👆 请回复 '是' 或 '否' 来确认\n",
#         title="[bold bright_blue]需要您的确认[/bold bright_blue]",
#         border_style="bright_blue",
#         padding=(1, 2),
#         width=80
#     )
#     console.print(confirm_panel)
#
#     # 添加分隔线
#     console.print("─" * 80, style="dim")
#
#     return f"AGENT_PAUSED_CONFIRM: {question} | 默认: {default_text}"
#
#
# @tool
# def request_auth(resource: str, permission: str, details: str = "") -> str:
#     """Request user authorization to access specific resources or perform specific operations.
#
#     Args:
#         resource: The name of the resource that needs to be accessed
#         permission: The type of permission required
#         details: Detailed description of the authorization (optional)
#
#     Returns:
#         Returns a message indicating user authorization is needed, causing the agent to stop current task execution
#     """
#
#     auth_panel = Panel(
#         f"🔐 [bold bright_yellow]需要授权访问: {resource}[/bold bright_yellow]\n\n"
#         f"🔑 权限类型: [cyan]{permission}[/cyan]\n"
#         f"📝 详细说明: [green]{details if details else '无额外说明'}[/green]\n\n"
#         f"👆 请确认是否授权此操作\n",
#         title="[bold bright_magenta]需要您的授权[/bold bright_magenta]",
#         border_style="bright_magenta",
#         padding=(1, 2),
#         width=80
#     )
#     console.print(auth_panel)
#
#     # 添加分隔线
#     console.print("─" * 80, style="dim")
#
#     return f"AGENT_PAUSED_AUTH: 资源={resource} | 权限={permission} | 详情={details}"
