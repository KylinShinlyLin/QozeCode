# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode Agent 启动器 - Inquirer版本
提供键盘上下选择的模型选择界面
"""
import os
import sys
import time
import configparser
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


def get_ollama_status():
    """获取 Ollama 配置状态（安静模式，不触发错误提示）"""
    try:
        # 直接读取配置文件，不调用会触发错误提示的函数
        config_dir = "/etc/conf"
        config_file = os.path.join(config_dir, "qoze.conf")
        fallback_dir = os.path.expanduser("~/.qoze")
        fallback_file = os.path.join(fallback_dir, "qoze.conf")

        cfg = configparser.ConfigParser()
        if os.path.exists(config_file):
            cfg.read(config_file)
        elif os.path.exists(fallback_file):
            cfg.read(fallback_file)
        else:
            return "未配置"

        if not cfg.has_section("Ollama"):
            return "未配置"

        host = cfg.get("Ollama", "host", fallback="http://localhost:11434")
        model = cfg.get("Ollama", "model", fallback="llama3.1")

        if not host or not model:
            return "未配置"

        model_clean = model.strip("'\"")
        host_clean = host.strip("'\"")
        return model_clean
    except Exception:
        return "未配置"


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

    # 获取 Ollama 状态
    ollama_status = get_ollama_status()

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

    # 获取 Ollama 模型名称（如果已配置）
    ollama_model = get_ollama_status()
    ollama_display = f"{ollama_model:<30} Ollama" if ollama_model != "未配置" else "ollama                         Ollama"

    # 定义选项 - 简洁对齐
    # 保持原有显示格式，但逻辑中我们会根据字符串反推
    choices = [
        "gemini-3.1-pro     (think)     vertex-ai",
        "gemini-3-flash     (think)     vertex-ai",
        "kimi-k2.5                      MoonShot",
        "kimi-for-coding                MoonShot",
        "gpt-5.4                        LiteLLM",
        "gpt-5.2                        LiteLLM",
        "gpt-5.2-chat-latest            LiteLLM",
        "Grok 4.1 Fast      (think)     XAI",
        "glm-5                          智普",
        "deepseek-reasoner  (think)     DeepSeek",
        "deepseek-chat                  DeepSeek",
        "gpt-5.2                        OpenAI",
        ollama_display,
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
        elif "Ollama" in selected:
            provider = ModelProvider.OLLAMA

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
        elif "glm-5" in selected:
            model_type = ModelType.GLM_5
        elif "Ollama" in selected:
            model_type = ModelType.OLLAMA

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
