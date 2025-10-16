# 顶部模块区（增加日志工具）
# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode Agent 启动器 - Inquirer版本
提供键盘上下选择的模型选择界面
"""
import os
import sys
import time
import traceback
from typing import Optional

# 导入共享的 console 实例
from shared_console import console

START_TIME = time.perf_counter()
LOG_DIR = os.path.expanduser("~/.qoze")
LOG_FILE = os.path.join(LOG_DIR, "launcher.log")

try:
    t_import = time.perf_counter()
    import inquirer
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.align import Align
except ImportError as e:
    print(f"错误详情: {e}")
    sys.exit(1)

template_content = """[openai]
api_key=

[deepseek]
api_key=

[aws]
session_token=
region_name=us-east-1

[vertexai]
project=
location=us-central1
credentials_path=

[ZHIPU]
api_key=
"""


def print_banner():
    """打印ASCII艺术风格的启动横幅"""
    ascii_art = """
██████╗  ██████╗ ███████╗███████╗     ██████╗ ██████╗ ██████╗ ███████╗
██╔═══██╗██╔═══██╗╚══███╔╝██╔════╝    ██╔════╝██╔═══██╗██╔══██╗██╔════╝
██║   ██║██║   ██║  ███╔╝ █████╗      ██║     ██║   ██║██║  ██║█████╗  
██║▄▄ ██║██║   ██║ ███╔╝  ██╔══╝      ██║     ██║   ██║██║  ██║██╔══╝  
╚██████╔╝╚██████╔╝███████╗███████╗    ╚██████╗╚██████╔╝██████╔╝███████╗
 ╚══▀▀═╝  ╚═════╝ ╚══════╝╚══════╝     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
"""
    subtitle = Text("使用 ↑↓ 选择，回车确认", style="dim")
    colored_art = Text(ascii_art, style="bold bright_cyan")
    content = Align.center(colored_art + "\n" + subtitle)
    panel = Panel(
        content,
        border_style="cyan",
        padding=(1, 2)
    )
    console.print(panel)
    console.print()


# 函数 get_model_choice（记录交互耗时）
def get_model_choice() -> Optional[str]:
    """获取用户的模型选择 - 支持键盘上下选择"""
    console.clear()

    # 显示横幅
    print_banner()

    # 定义选项 - 简洁对齐
    choices = [
        "Claude-4      Anthropic",
        "Gemini        Google GCP",
        "GPT-5         OpenAI",
        # "GPT-5-Codex   OpenAI",
        "DeepSeek      DeepSeek",
        "GLM-4         智普",
        "[退出程序]"
    ]

    questions = [
        inquirer.List(
            'model',
            message="选择模型",
            choices=choices,
            carousel=True
        )
    ]

    try:
        answers = inquirer.prompt(questions)
        if answers is None:
            return None
        selected = answers['model']
        # 根据选择返回对应的模型名
        if "Claude-4" in selected:
            return 'claude-4'
        elif "Gemini" in selected:
            return 'gemini'
        elif "GPT-5-Codex" in selected:
            return 'gpt-5-codex'
        elif "GPT-5" in selected:
            return 'gpt-5'
        elif "DeepSeek" in selected:
            return 'DeepSeek'
        elif "GLM-4" in selected:
            return 'GLM-4'
        elif "退出" in selected:
            console.print("\n👋 再见", style="dim")
            return None

    except KeyboardInterrupt:
        console.print("\n👋 再见", style="dim")
        return None


# 判断配置文件是否存在，如果不存在则创建一个
# 函数 ensure_config（记录文件检查与创建耗时）
def ensure_config():
    config_dir = "/etc/conf"
    config_file = os.path.join(config_dir, "qoze.conf")
    fallback_dir = os.path.expanduser("~/.qoze")
    fallback_file = os.path.join(fallback_dir, "qoze.conf")

    if os.path.exists(config_file) or os.path.exists(fallback_file):
        return

    try:
        os.makedirs(config_dir, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(template_content)
        return
    except Exception:
        pass

    try:
        os.makedirs(fallback_dir, exist_ok=True)
        with open(fallback_file, "w", encoding="utf-8") as f:
            f.write(template_content)
    except Exception as e:
        console.print(f"创建配置文件失败: {e}", style="red")


# 函数 launch_agent（记录启动与返回耗时）
def launch_agent(model: str):
    """启动 QozeCode Agent"""
    console.clear()
    from qoze_code_agent import handleRun
    # 直接调用 handleRun 并传入选择的模型
    handleRun(model_name=model, session_id='123')


# 函数 main（记录各阶段耗时）
def main():
    """主函数"""
    try:
        ensure_config()
        # 获取模型选择
        model = get_model_choice()

        if model is None:
            return

        # 启动 agent
        launch_agent(model)

    except KeyboardInterrupt:
        console.print("\n👋 再见", style="dim")
    except Exception as e:
        console.print(f"\n❌ 错误: {str(e)}", style="red", markup=False)


if __name__ == '__main__':
    main()
