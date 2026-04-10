# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode Agent 启动器 - Inquirer版本
提供键盘上下选择的模型选择界面
"""
import os
import sys
import time
from typing import Optional, Tuple

from constant import template_content
from enums import ModelProvider, ModelType

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
    from rich.padding import Padding
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
    # 使用 Padding 代替 Panel 去掉边框
    console.print(Padding(content, (1, 2)))
    console.print()


# 函数 get_model_choice（记录交互耗时）
def get_model_choice() -> Optional[Tuple[ModelProvider, ModelType]]:
    """获取用户的模型选择 - 支持键盘上下选择"""
    console.clear()

    # 显示横幅
    print_banner()

    # 定义选项 - 简洁对齐
    # 保持原有显示格式，但逻辑中我们会根据字符串反推
    choices = [
        "gemini-3.1-pro     (think)     vertex-ai",
        "gemini-3-flash     (think)     vertex-ai",
        "kimi-k2.5                      MoonShot",
        "kimi-for-coding                MoonShot",
        "qwen3.6-plus       (think)     Alibaba Cloud",
        "glm-5                          智普",
        "glm-5v-turbo                   智普",
        "gpt-5.4                        LiteLLM",
        # "gpt-5.2                        LiteLLM",
        # "gpt-5.2-chat-latest            LiteLLM",
        # "Grok 4.1 Fast      (think)     XAI",
        "deepseek-reasoner  (think)     DeepSeek",
        "deepseek-chat                  DeepSeek",
        # "gpt-5.2                        OpenAI",
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

        if "退出" in selected:
            console.print("👋 再见", style="dim")
            os.system("cls" if os.name == "nt" else "clear")
            return None

        provider = None
        model_type = None

        # 1. 解析 Provider
        if "vertex-ai" in selected:
            provider = ModelProvider.VERTEX_AI
        elif "XAI" in selected:
            provider = ModelProvider.XAI
        elif "LiteLLM" in selected:
            provider = ModelProvider.LITELLM
        elif "bedrock" in selected:
            provider = ModelProvider.BEDROCK
        elif "DeepSeek" in selected:
            provider = ModelProvider.DEEPSEEK
        elif "OpenAI" in selected:
            provider = ModelProvider.OPENAI
        elif "MoonShot" in selected:
            provider = ModelProvider.MOONSHOT
        elif "智普" in selected:
            provider = ModelProvider.ZHIPU
        elif "Alibaba Cloud" in selected:
            provider = ModelProvider.ALIBABA_CLOUD
        elif "qwen3.6-plus" in selected:
            provider = ModelProvider.ALIBABA_CLOUD

        # 2. 解析 ModelType
        # if "gemini-3-pro" in selected:
        #     model_type = ModelType.GEMINI_3_PRO
        if "gemini-3.1-pro" in selected:
            model_type = ModelType.GEMINI_3_1_PRO
        elif "gemini-3-flash" in selected:
            model_type = ModelType.GEMINI_3_FLASH
        elif "claude-haiku-4-5" in selected:
            model_type = ModelType.CLAUDE_4_5_HAIKU
        elif "claude-sonnet-4-6" in selected:
            model_type = ModelType.CLAUDE_4_6_SONNET
        elif "claude-opus-4-6" in selected:
            model_type = ModelType.CLAUDE_4_6_OPUS
        elif "Grok" in selected:
            model_type = ModelType.GROK_4_1_FAST
        elif "gpt-5.2-codex" in selected:
            model_type = ModelType.GPT_5_2_CODEX
        elif "gpt-5.4" in selected:
            model_type = ModelType.GPT_5_4
        elif "gpt-5.2" in selected:
            model_type = ModelType.GPT_5_2
        elif "kimi-for-coding" in selected:
            model_type = ModelType.KIMI_FOR_CODING
        elif "kimi-k2.5" in selected:
            model_type = ModelType.KIMI_K2_5
        elif "deepseek-reasoner" in selected:
            model_type = ModelType.DEEPSEEK_REASONER
        elif "deepseek-chat" in selected:
            model_type = ModelType.DEEPSEEK_CHAT
        elif "kimi-2.5" in selected:
            model_type = ModelType.KIMI_2_5
        elif "glm-4.6" in selected:
            model_type = ModelType.GLM_4_6
        elif "qwen3-max" in selected:
            model_type = ModelType.QWEN_3_MAX
        elif "qwen3.6-plus" in selected:
            model_type = ModelType.QWEN_3_6_PLUS
        elif "glm-5v-turbo" in selected:
            model_type = ModelType.GLM_5V_TURBO
        elif "glm-5" in selected:
            model_type = ModelType.GLM_5

        if provider and model_type:
            return provider, model_type

        console.print(f"无法解析选项: {selected}", style="red")
        return None

    except KeyboardInterrupt:
        console.print("👋 再见", style="dim")
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
