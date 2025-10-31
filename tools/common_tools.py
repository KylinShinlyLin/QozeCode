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
