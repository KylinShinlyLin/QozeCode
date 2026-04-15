"""
配置管理模块
- 统一在 /etc/conf/qoze.conf 维护模型密钥
- 缺少写权限时回退到 ~/.qoze/qoze.conf，并提示用户
- 首次选择模型时若缺少密钥，交互式提示输入并保存
"""

import configparser
import os
from typing import Tuple, Dict, Union

from shared_console import console
from enums import ModelProvider, ModelType

CONFIG_DIR = "/etc/conf"
CONFIG_FILE = os.path.join(CONFIG_DIR, "qoze.conf")
FALLBACK_DIR = os.path.expanduser("~/.qoze")
FALLBACK_FILE = os.path.join(FALLBACK_DIR, "qoze.conf")


def get_tavily_key() -> str:
    """
    获取 Tavily API Key
    """
    cfg, _ = _load_config()

    section = "tavily"
    if not cfg.has_section(section):
        fail("Tavily API Key (section [tavily] -> tavily_key)")

    tavily_key = cfg.get(section, "tavily_key", fallback=None)
    if not tavily_key:
        fail("Tavily API Key (section [tavily] -> tavily_key)")

    return tavily_key.strip("\"'")


def get_soniox_key() -> str:
    """
    获取 Soniox API Key
    """
    cfg, _ = _load_config()

    section = "soniox"
    if not cfg.has_section(section):
        return None

    soniox_key = cfg.get(section, "api_key", fallback=None)
    if not soniox_key:
        return None

    return soniox_key.strip("\"'")


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
            f"🔴  未检测到 {missing_desc}。",
            "请在当前机器的配置文件中添加必要的 key：",
            f"- 配置文件: {current_cfg_path}",
        ]),
        style="yellow"
    )
    raise RuntimeError(f"缺少模型配置：{missing_desc}")


def ensure_model_credentials(model_identifier: Union[str, ModelProvider]) -> Dict[str, str]:
    """
    确保对应模型的密钥存在：
    - 若缺失则提示用户去配置文件添加
    """
    cfg, _ = _load_config()

    # 统一化标识符处理
    # model_initializer 可能会传递字符串（如 "Claude-4", "gpt-5.2"）或 ModelType.value
    # 我们将其映射到对应的 Config Section

    # 1. OpenAI
    if model_identifier in ("gpt-5.2", "gpt-5.1", "gpt-5-codex", "OpenAI"):
        section = "OpenAI"
        required_keys = ["api_key"]

    # 2. LiteLLM
    elif model_identifier == "LiteLLM":
        section = "LiteLLM"
        required_keys = ["api_key", "base_url"]

    # 3. XAI (Grok)
    elif model_identifier in ("Grok-4.1-Fast", "XAI"):
        section = "XAI"
        required_keys = ["api_key"]

    # 4. DeepSeek
    elif model_identifier in ("deepseek-chat", "deepseek-reasoner", "DeepSeek"):
        section = "DeepSeek"
        required_keys = ["api_key"]

    # 6. Vertex AI (Gemini)
    elif model_identifier in ("gemini-3.1-pro", "gemini-3-flash", "VertexAi"):
        section = "VertexAi"
        if not cfg.has_section(section):
            fail(f"Gemini/Vertex AI 凭证 (section [{section}])")

        project = cfg.get(section, "project", fallback=None)
        location = cfg.get(section, "location", fallback="global")
        cred_path = cfg.get(section, "credentials_path", fallback=None)

        if not project:
            fail(f"Vertex AI (section [{section}] -> project)")
        if not cred_path:
            fail(f"Vertex AI (section [{section}] -> credentials_path)")

        return {"project": project, "location": location, "credentials_path": cred_path}

    # 7. ZHIPU (GLM)
    elif model_identifier == "ZHIPU":
        section = "ZHIPU"
        if not cfg.has_section(section):
            fail(f"缺少 (section [{section}]) 配置")

        api_key = cfg.get(section, "api_key", fallback=None)
        base_url = cfg.get(section, "base_url", fallback=None)
        return {"api_key": api_key, "base_url": base_url}

    # 8. Qwen (Alibaba)
    elif model_identifier in ("qwen3-max", "qwen3.6-plus", "Qwen3", "Qwen3.6-Plus"):
        section = "Qwen3"
        required_keys = ["api_key"]

    # 9. Kimi (Moonshot)
    elif model_identifier in ("kimi-k2.5", "Kimi"):
        section = "Kimi"
        required_keys = ["api_key"]

    # 10. Kimi For Coding
    elif model_identifier in ("kimi-for-coding", "KimiCode"):
        section = "KimiCode"
        required_keys = ["api_key"]

    else:
        # 尝试直接作为 section name
        section = str(model_identifier)
        required_keys = ["api_key"]

    # 通用检查逻辑
    if not cfg.has_section(section):
        fail(f"{model_identifier} 凭证 (section [{section}])")

    creds = {}
    for key in required_keys:
        val = cfg.get(section, key, fallback=None)
        if not val:
            fail(f"{model_identifier} 凭证 (section [{section}] -> {key})")
        creds[key] = val

    if section == "Kimi":
        creds["base_url"] = cfg.get(section, "base_url", fallback=None)
    if section == "KimiCode":
        creds["base_url"] = cfg.get(section, "base_url", fallback=None)

    return creds


def get_proxy_config() -> Dict[str, Union[str, int, None]]:
    """
    获取代理配置
    Returns:
        dict: 包含 host 和 port 的字典，如果没有配置则返回 None
    """
    cfg, _ = _load_config()

    section = "proxy"
    if not cfg.has_section(section):
        return None

    host = cfg.get(section, "host", fallback=None)
    port = cfg.get(section, "port", fallback=None)

    if not host or not port:
        return None

    try:
        port = int(port)
    except ValueError:
        return None

    return {"host": host.strip(), "port": port}
