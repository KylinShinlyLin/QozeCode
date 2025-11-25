"""
配置管理模块
- 统一在 /etc/conf/qoze.conf 维护模型密钥
- 缺少写权限时回退到 ~/.config/qoze/qoze.conf，并提示用户
- 首次选择模型时若缺少密钥，交互式提示输入并保存
"""

import configparser
import os
from typing import Tuple, Dict

from shared_console import console

CONFIG_DIR = "/etc/conf"
CONFIG_FILE = os.path.join(CONFIG_DIR, "qoze.conf")
FALLBACK_DIR = os.path.expanduser("~/.qoze")
FALLBACK_FILE = os.path.join(FALLBACK_DIR, "qoze.conf")


def _ensure_dir(path: str):
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except PermissionError:
        return False


def _load_config() -> Tuple[configparser.ConfigParser, str]:
    cfg = configparser.ConfigParser()
    # 优先读取 /etc/conf，其次读取用户目录
    if os.path.exists(CONFIG_FILE):
        cfg.read(CONFIG_FILE)
        return cfg, CONFIG_FILE
    if os.path.exists(FALLBACK_FILE):
        cfg.read(FALLBACK_FILE)
        return cfg, FALLBACK_FILE
    # 两边都不存在则创建对象，稍后保存
    return cfg, CONFIG_FILE


def _save_config(cfg: configparser.ConfigParser) -> str:
    # 优先尝试写入 /etc/conf
    if _ensure_dir(CONFIG_DIR):
        try:
            with open(CONFIG_FILE, "w") as f:
                cfg.write(f)
            return CONFIG_FILE
        except PermissionError:
            pass
    # 回退用户目录
    _ensure_dir(FALLBACK_DIR)
    with open(FALLBACK_FILE, "w") as f:
        cfg.write(f)
    return FALLBACK_FILE


def get_config_path() -> str:
    _, path = _load_config()
    return path


def fail(missing_desc: str):
    current_cfg_path = get_config_path()
    console.print(
        "\n".join([
            f"🔑 未检测到 {missing_desc}。",
            "请在当前机器的配置文件中添加必要的 key：",
            f"- 配置文件: {current_cfg_path}",
        ]),
        style="yellow"
    )
    raise RuntimeError(f"缺少模型凭证：{missing_desc}")


def ensure_model_credentials(model_name: str) -> Dict[str, str]:
    """
    确保对应模型的密钥存在：
    - 若缺失则提示用户去配置文件添加
    """
    cfg, _ = _load_config()

    if model_name in ("gpt-5", "gpt-5.1", "gpt-5-codex"):
        section = "openai"
        if not cfg.has_section(section):
            fail("OpenAI API Key (section [openai] -> api_key)")
        api_key = cfg.get(section, "api_key", fallback=None)
        if not api_key:
            fail("OpenAI API Key (section [openai] -> api_key)")
        return {"api_key": api_key}

    if model_name == "DeepSeek":
        section = "deepseek"
        if not cfg.has_section(section):
            fail("DeepSeek API Key (section [deepseek] -> api_key)")
        api_key = cfg.get(section, "api_key", fallback=None)
        if not api_key:
            fail("DeepSeek API Key (section [deepseek] -> api_key)")
        return {"api_key": api_key}

    if model_name == "claude-4":
        section = "aws"
        if not cfg.has_section(section):
            fail("AWS Bedrock 凭证 (section [aws])")
        session_token = cfg.get(section, "session_token", fallback=None)  # 支持临时凭证
        region = cfg.get(section, "region_name", fallback="us-east-1")
        if not session_token:
            fail("AWS Bedrock 凭证 (session_token)")

        os.environ['AWS_BEARER_TOKEN_BEDROCK'] = session_token
        credentials = {
            "aws_session_token": session_token,
            "region_name": region,
        }
        return credentials
    if model_name == "gemini":
        section = "vertexai"
        if not cfg.has_section(section):
            fail("Gemini/Vertex AI 凭证 (section [vertexai])")
        project = cfg.get(section, "project", fallback=None)
        location = cfg.get(section, "location", fallback="us-central1")
        cred_path = cfg.get(section, "credentials_path", fallback=None)
        if not project or not cred_path:
            fail("Gemini/Vertex AI 凭证 (project/credentials_path)")
        return {"project": project, "location": location, "credentials_path": cred_path}

    if model_name == "GLM-4":
        section = "ZHIPU"
        if not cfg.has_section(section):
            fail("GLM-4 AI 凭证 (section [ZHIPU])")
        api_key = cfg.get(section, "api_key", fallback=None)
        if not api_key:
            fail("GLM-4 AI 凭证")
        return {"api_key": api_key}
    if model_name == "Kimi":
        section = "Kimi"
        if not cfg.has_section(section):
            fail("Kimi AI 凭证 (section [Kimi])")
        api_key = cfg.get(section, "api_key", fallback=None)
        if not api_key:
            fail("Kimi AI 凭证")
        return {"api_key": api_key}

    if model_name == "Qwen3":
        section = "Qwen3"
        if not cfg.has_section(section):
            fail("Qwen3 AI 凭证 (section [Qwen3])")
        api_key = cfg.get(section, "api_key", fallback=None)
        if not api_key:
            fail("Qwen3 AI 凭证")
        return {"api_key": api_key}

    raise ValueError(f"不支持的模型: {model_name}")
