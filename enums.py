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


class ModelType(Enum):
    """模型类型枚举 (对应 launcher.py 的返回值)"""
    GEMINI_3_PRO = "gemini-3-pro"
    GEMINI_3_FLASH = "gemini-3-flash"
    GROK_4_1_FAST = "Grok-4.1-Fast"
    GPT_5_2 = "gpt-5.2"
    CLAUDE_4 = "claude-4"
    KIMI_2_5 = "Kimi 2.5"
    QWEN_3_MAX = "qwen3-max"
    DEEPSEEK_REASONER = "deepseek-reasoner"
    DEEPSEEK_CHAT = "deepseek-chat"
    GLM_4_6 = "glm-4.6"
    GLM_5 = "glm-5"


# 厂商与模型的映射关系建议（注：GPT_5_2 在 launcher 中同时对应 LiteLLM 和 OpenAI 两种选项）
MODEL_PROVIDER_MAP = {
    ModelType.GEMINI_3_PRO: ModelProvider.VERTEX_AI,
    ModelType.GEMINI_3_FLASH: ModelProvider.VERTEX_AI,
    ModelType.GROK_4_1_FAST: ModelProvider.XAI,
    # ModelType.GPT_5_2: [ModelProvider.LITELLM, ModelProvider.OPENAI], # 特殊情况
    ModelType.CLAUDE_4: ModelProvider.BEDROCK,
    ModelType.KIMI_2_5: ModelProvider.MOONSHOT,
    ModelType.QWEN_3_MAX: ModelProvider.ALIBABA_CLOUD,
    ModelType.DEEPSEEK_REASONER: ModelProvider.DEEPSEEK,
    ModelType.DEEPSEEK_CHAT: ModelProvider.DEEPSEEK,
    ModelType.GLM_4_6: ModelProvider.ZHIPU,
}
