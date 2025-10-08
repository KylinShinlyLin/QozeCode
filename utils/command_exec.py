import subprocess
import time
from typing import Optional

from rich.panel import Panel
from shared_console import console


def run_command(command: str) -> str:
    """
    直接执行系统命令，实时输出到控制台，并返回完整输出文本。
    适用于聊天循环中处理以 '!' 开头的输入。
    """

    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        start_time = time.time()
        output_lines = []

        # 流式读取输出
        while True:
            if process.stdout is None:
                break

            line = process.stdout.readline()
            if line:
                output_lines.append(line)
                console.print(line.rstrip())

            # 进程结束
            if line == "" and process.poll() is not None:
                break

            # # 超时处理
            # if time.time() - start_time > timeout:
            #     try:
            #         process.kill()
            #     except Exception:
            #         pass
            #     output_lines.append(f"\n⚠️ 命令执行超时 ({timeout}秒)，进程已终止。")
            #     break

        exit_code: Optional[int] = process.poll()
        full_output = "".join(output_lines)

        return full_output

    except Exception as e:
        error_msg = f"❌:{str(e)}"
        return error_msg
