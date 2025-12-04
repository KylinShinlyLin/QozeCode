from langchain_core.tools import tool
from rich.markdown import Markdown
from rich.panel import Panel

# 导入共享的 console 实例
from shared_console import console
from crontab import CronTab
import getpass
import subprocess
import platform


@tool
def manage_cron_job(action: str, command: str = None, schedule: str = None, comment: str = None) -> str:
    """Manage macOS system cron jobs (scheduled tasks).

    Use this tool to list, add, or remove scheduled tasks in the system's crontab.

    Args:
        action: The operation to perform. Options:
            - 'list': Show all current cron jobs.
            - 'add': Add a new cron job. Requires 'command' and 'schedule'.
            - 'remove': Remove a cron job. Requires 'comment' (recommended) or 'command' to identify the job.
        command: The shell command to run. Required for 'add'.
        schedule: The cron schedule expression (e.g., '*/5 * * * *' for every 5 mins, '0 9 * * 1' for every Monday at 9am). Required for 'add'.
        comment: A unique identifier for the job. Highly recommended for 'add' and 'remove' to easily identify tasks.

    Returns:
        A status message describing the outcome of the operation.
    """
    try:
        current_user = getpass.getuser()
        cron = CronTab(user=current_user)

        result_msg = ""

        if action == "list":
            jobs = list(cron)
            if not jobs:
                result_msg = "No cron jobs found for user: " + current_user
            else:
                lines = [f"**User: {current_user}**"]
                for job in jobs:
                    sched = str(job.slices).strip()
                    cmd = job.command
                    cmt = f" ({job.comment})" if job.comment else ""
                    lines.append(f"- `{sched}`: `{cmd}`{cmt}")
                result_msg = "\n".join(lines)

        elif action == "add":
            if not command or not schedule:
                return "❌ Error: 'command' and 'schedule' are required for adding a job."

            # 创建新任务
            job = cron.new(command=command, comment=comment if comment else "")

            # 设置时间
            try:
                job.setall(schedule)
            except KeyError:
                return f"❌ Error: Invalid cron schedule expression '{schedule}'"

            if not job.is_valid():
                return "❌ Error: Job configuration is invalid."

            cron.write()
            result_msg = f"✅ Successfully added cron job:\nCommand: `{command}`\nSchedule: `{schedule}`\nComment: {comment}"

        elif action == "remove":
            if not comment and not command:
                return "❌ Error: Please provide 'comment' or 'command' to identify the job to remove."

            removed_count = 0
            # 优先通过 comment 查找
            if comment:
                iter = cron.find_comment(comment)
                for job in iter:
                    cron.remove(job)
                    removed_count += 1
            # 其次通过 command 查找
            elif command:
                iter = cron.find_command(command)
                for job in iter:
                    cron.remove(job)
                    removed_count += 1

            if removed_count > 0:
                cron.write()
                result_msg = f"✅ Successfully removed {removed_count} cron job(s)."
            else:
                result_msg = "⚠️ No matching cron jobs found to remove."

        else:
            return f"❌ Error: Unknown action '{action}'. Use 'list', 'add', or 'remove'."

        # 显示结果
        panel = Panel(
            Markdown(result_msg),
            title="[bold blue]Cron Job Manager[/bold blue]",
            border_style="blue",
            padding=(0, 2)
        )
        console.print(panel)

        return result_msg

    except Exception as e:
        error_msg = f"❌ System Error: {str(e)}"
        console.print(Panel(error_msg, style="red"))
        return error_msg


@tool
def schedule_one_off_task(command: str, time_str: str) -> str:
    """Schedule a one-off (one-time) task using the system's 'at' command.

    Use this tool to execute a command once at a specific future time.
    This ensures the task runs even if the main program exits.
    Supports macOS and Linux.

    Args:
        command: The shell command to run.
        time_str: Time specification string supported by 'at'.
                  Examples: 'now + 30 minutes', '17:00', 'tomorrow', 'now + 2 days'.

    Returns:
        Confirmation message from the 'at' command.
    """
    try:
        # Check if 'at' is installed
        if subprocess.call(["which", "at"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            return "❌ Error: 'at' command not found. Please install it (e.g., 'brew install at' on macOS or 'apt install at' on Linux)."

        # MacOS specific check
        warning = ""
        if platform.system() == "Darwin":
            try:
                # Check if atrun is loaded using launchctl
                check = subprocess.run("launchctl list | grep atrun", shell=True, stdout=subprocess.PIPE)
                if check.returncode != 0:
                    warning = "\n\n⚠️ **Warning for macOS users**: The `atrun` service appears to be disabled.\n"                               "The task is scheduled but **will not execute** until you enable the service.\n"                               "Run this in terminal: `sudo launchctl load -w /System/Library/LaunchDaemons/com.apple.atrun.plist`"
            except Exception:
                pass  # Ignore check failures

        # Construct the command
        # echo "command" | at time_str
        process = subprocess.Popen(['at', time_str], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(input=command)

        if process.returncode == 0:
            # stderr often contains the "job X at Y" confirmation message for 'at'
            msg = f"✅ Task scheduled.\n**Command**: `{command}`\n**Time**: `{time_str}`\n**System Output**: {stderr.strip() or stdout.strip()}"
            if warning:
                msg += warning

            panel = Panel(
                Markdown(msg),
                title="[bold blue]One-off Task Scheduler[/bold blue]",
                border_style="blue",
                padding=(0, 2)
            )
            console.print(panel)
            return msg
        else:
            err_msg = f"❌ Failed to schedule task.\nError: {stderr.strip()}"
            console.print(Panel(err_msg, style="red"))
            return err_msg

    except Exception as e:
        error_msg = f"❌ System Error: {str(e)}"
        console.print(Panel(error_msg, style="red"))
        return error_msg
