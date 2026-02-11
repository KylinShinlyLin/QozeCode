# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode Agent 启动器 - Inquirer版本
提供键盘上下选择的模型选择界面
"""
import os
import sys
import time
from typing import Optional

from constant import template_content

# 屏蔽 absl 库的 STDERR 警告
os.environ.setdefault('ABSL_LOGGING_VERBOSITY', '1')  # 只显示 WARNING 及以上级别
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')  # 屏蔽 TensorFlow 信息和警告

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
        "gemini-3-pro       (think)     Google GCP",
        "gemini-3-flash     (think)     Google GCP",
        "Grok 4.1 Fast      (think)     XAI",
        "gpt-5.2-chat-latest            LiteLLM",
        "Claude-4                       bedrock",
        "Kimi 2.5           (think)     月之暗面",
        "Claude-4           (think)     bedrock",
        "qwen3-max          (think)     Alibaba Cloud",
        "deepseek-reasoner  (think)     DeepSeek R1",
        "deepseek-chat                  DeepSeek V3",
        "gpt-5.2                        OpenAI",
        "glm-4.6                        智普",
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
            return 'Claude-4'
        elif "gemini-3-pro" in selected:
            return 'gemini-3-pro'
        elif "gemini-3-flash" in selected:
            return 'gemini-3-flash'
        elif "Grok 4.1 Fast" in selected:
            return 'Grok-4.1-Fast'
        elif "gpt-5.2" in selected:
            return 'gpt-5.2'
        elif "deepseek-reasoner" in selected:
            return 'deepseek-reasoner'
        elif "deepseek-chat" in selected:
            return 'deepseek-chat'
        elif "glm-4.6" in selected:
            return 'glm-4.6'
        elif "qwen3-max" in selected:
            return 'qwen3-max'
        elif "Kimi 2.5" in selected:
            return 'Kimi 2.5'
        elif "退出" in selected:
            console.print("\n👋 再见", style="dim")
            return None

    except KeyboardInterrupt:
        console.print("\n👋 再见", style="dim")
        return None


def ensure_config():
    # 区分系统环境 配置文件
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
