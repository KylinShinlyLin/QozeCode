from enum import Enum


class ModelProvider(Enum):
    """模型厂商枚举"""
    VERTEX_AI = "VertexAi"
    XAI = "XAI"
    LITELLM = "LiteLLM"
    BEDROCK = "Bedrock"
    MOONSHOT = "月之暗面"
    ALIBABA_CLOUD = "Alibaba Cloud"
    DEEPSEEK = "DeepSeek"
    OPENAI = "OpenAI"
    ZHIPU = "ZHIPU"
    XIAOMI = "小米"


class ModelType(Enum):
    """模型类型枚举 (对应 launcher.py 的返回值)"""
    GEMINI_3_1_PRO = "gemini-3.1-pro"
    # GEMINI_3_PRO = "gemini-3-pro"
    GEMINI_3_FLASH = "gemini-3-flash"
    GEMINI_3_5_FLASH = "gemini-3.5-flash"
    GROK_4_1_FAST = "Grok-4.1-Fast"
    GPT_5_4 = "gpt-5.4"
    GPT_5_2 = "gpt-5.2"
    GPT_5_2_CODEX = "gpt-5.2-codex"
    KIMI_K2_5 = "kimi-k2.5"
    KIMI_FOR_CODING = "kimi-for-coding"
    # CLAUDE_4 = "claude-4"
    # CLAUDE_4_6_SONNET = "claude-sonnet-4-6"
    # CLAUDE_4_6_OPUS = "claude-opus-4-6"
    # CLAUDE_4_5_HAIKU = "claude-haiku-4-5"
    KIMI_2_5 = "Kimi 2.5"
    QWEN_3_MAX = "qwen3-max"
    QWEN_3_6_PLUS = "qwen3.6-plus"
    DEEPSEEK_REASONER = "deepseek-v4-pro"
    DEEPSEEK_CHAT = "deepseek-v4-flash"
    GLM_4_6 = "glm-4.6"
    GLM_5 = "glm-5"
    GLM_5V_TURBO = "glm-5v-turbo"
    MIMO_V2_5_PRO = "mimo-v2.5-pro"


# 模型视觉（图片输入）支持映射表
# True = 支持图片输入（多模态），False = 仅支持文本
MODEL_VISION_SUPPORT = {
    ModelType.GEMINI_3_1_PRO: True,      # Gemini 原生多模态
    ModelType.GEMINI_3_FLASH: True,       # Gemini 原生多模态
    ModelType.GEMINI_3_5_FLASH: True,     # Gemini 原生多模态
    ModelType.GROK_4_1_FAST: False,       # Grok API 不支持图片输入
    ModelType.GPT_5_4: True,              # OpenAI GPT 支持视觉
    ModelType.GPT_5_2: True,              # OpenAI GPT 支持视觉
    ModelType.GPT_5_2_CODEX: True,        # OpenAI GPT 支持视觉
    ModelType.KIMI_K2_5: True,            # Kimi k2.5 支持图片输入
    ModelType.KIMI_FOR_CODING: True,      # 专用编程模型，支持视觉
    ModelType.KIMI_2_5: True,             # Kimi 2.5 支持图片输入
    ModelType.QWEN_3_MAX: True,           # Qwen 支持多模态
    ModelType.QWEN_3_6_PLUS: True,        # Qwen 支持多模态
    ModelType.DEEPSEEK_REASONER: False,   # DeepSeek 不支持图片输入
    ModelType.DEEPSEEK_CHAT: False,       # DeepSeek 不支持图片输入
    ModelType.GLM_4_6: False,             # GLM-4.6 纯文本模型
    ModelType.GLM_5: False,               # GLM-5 纯文本模型
    ModelType.GLM_5V_TURBO: True,         # GLM-5V-Turbo 多模态模型 (V=Vision)
    ModelType.MIMO_V2_5_PRO: False,       # 小米 MiMo 纯文本模型
}


def supports_vision(model_type: ModelType) -> bool:
    """查询指定模型是否支持视觉（图片输入）"""
    return MODEL_VISION_SUPPORT.get(model_type, False)


# 厂商与模型的映射关系建议（注：GPT_5_2 在 launcher 中同时对应 LiteLLM 和 OpenAI 两种选项）
MODEL_PROVIDER_MAP = {
    # ModelType.CLAUDE_4_6_SONNET: ModelProvider.LITELLM,
    # ModelType.CLAUDE_4_6_OPUS: ModelProvider.LITELLM,
    # ModelType.CLAUDE_4_5_HAIKU: ModelProvider.LITELLM,
    ModelType.KIMI_K2_5: ModelProvider.MOONSHOT,
    ModelType.KIMI_FOR_CODING: ModelProvider.MOONSHOT,
    ModelType.GPT_5_4: ModelProvider.LITELLM,
    ModelType.GEMINI_3_1_PRO: ModelProvider.VERTEX_AI,
    ModelType.GEMINI_3_FLASH: ModelProvider.VERTEX_AI,
    ModelType.GEMINI_3_5_FLASH: ModelProvider.VERTEX_AI,
    ModelType.GROK_4_1_FAST: ModelProvider.XAI,

    # ModelType.GPT_5_2: [ModelProvider.LITELLM, ModelProvider.OPENAI], # 特殊情况
    # ModelType.CLAUDE_4: ModelProvider.BEDROCK,
    ModelType.KIMI_2_5: ModelProvider.MOONSHOT,
    ModelType.QWEN_3_MAX: ModelProvider.ALIBABA_CLOUD,
    ModelType.QWEN_3_6_PLUS: ModelProvider.ALIBABA_CLOUD,
    ModelType.DEEPSEEK_REASONER: ModelProvider.DEEPSEEK,
    ModelType.DEEPSEEK_CHAT: ModelProvider.DEEPSEEK,
    ModelType.GLM_4_6: ModelProvider.ZHIPU,
    ModelType.MIMO_V2_5_PRO: ModelProvider.XIAOMI,
}
