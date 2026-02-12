"""
模型初始化模块
负责根据模型名称初始化对应的LLM实例
"""
from enums import ModelProvider, ModelType
from config_manager import ensure_model_credentials
import os


def patch_langchain_openai():
    """
    Patch langchain_openai to support reasoning_content in stream response
    This allows models like DeepSeek-R1 (via OpenAI API), GLM-5, etc., to return their reasoning process.
    """
    try:
        from langchain_openai.chat_models import base as chat_models_base
        from langchain_openai.chat_models.base import AIMessageChunk

        if hasattr(chat_models_base, "_is_patched_for_reasoning"):
            return

        original_convert = chat_models_base._convert_delta_to_message_chunk

        def patched_convert_delta_to_message_chunk(_dict, default_class):
            chunk = original_convert(_dict, default_class)
            if "reasoning_content" in _dict and isinstance(chunk, AIMessageChunk):
                chunk.additional_kwargs["reasoning_content"] = _dict["reasoning_content"]
            return chunk

        chat_models_base._convert_delta_to_message_chunk = patched_convert_delta_to_message_chunk
        chat_models_base._is_patched_for_reasoning = True
    except ImportError:
        pass
    except Exception as e:
        os.makedirs(".qoze", exist_ok=True)
        with open(".qoze/patch.log", "a") as f:
            f.write(f"OpenAI Patch failed: {str(e)}\n")


def patch_langchain_deepseek():
    """
    todo 先使用猴子补丁修复 deepseek-r1 思考过程不支持 function call 的问题
    针对 deepseek-reasoner 的强制要求，修复消息转换中丢失 reasoning_content 的问题。
    未来 通自定义实现或者，等待官方修复这个问题
    """
    try:
        from langchain_deepseek import ChatDeepSeek

        # 记录原始方法
        original_get_request_payload = ChatDeepSeek._get_request_payload

        def patched_get_request_payload(self, input_, **kwargs):
            # 1. 获取原始 payload
            payload = original_get_request_payload(self, input_, **kwargs)

            # 2. 获取原始消息对象列表
            messages = self._convert_input(input_).to_messages()

            # 3. 补全 reasoning_content
            if "messages" in payload:
                for i, msg in enumerate(messages):
                    if i < len(payload["messages"]):
                        # 尝试从 additional_kwargs 中提取
                        reasoning = msg.additional_kwargs.get("reasoning_content")

                        # 兼容：有些版本的 LangChain 会把 reasoning 放在 content 列表中
                        if not reasoning and isinstance(msg.content, list):
                            for block in msg.content:
                                if isinstance(block, dict) and block.get("type") == "reasoning_content":
                                    reasoning = block.get("reasoning_content")
                                    break

                        if reasoning:
                            payload["messages"][i]["reasoning_content"] = reasoning

            return payload

        # 替换类方法
        ChatDeepSeek._get_request_payload = patched_get_request_payload
    except Exception as e:
        # 确保 .qoze 目录存在
        os.makedirs(".qoze", exist_ok=True)
        with open(".qoze/patch.log", "a") as f:
            f.write(f"Patch failed: {str(e)}\n")


def get_gemini_model_name(model_type: ModelType):
    if model_type == ModelType.GEMINI_3_PRO:
        return "gemini-3-pro-preview"
    elif model_type == ModelType.GEMINI_3_FLASH:
        return "gemini-3-flash-preview"
    return None


def initialize_llm(provider: ModelProvider, model_type: ModelType):
    """根据模型厂商和类型初始化对应的LLM"""

    # 0. Global Patch for OpenAI compatible providers
    patch_langchain_openai()

    # 1. DeepSeek Patch
    if provider == ModelProvider.DEEPSEEK:
        patch_langchain_deepseek()

    # 2. Provider Switch
    if provider == ModelProvider.BEDROCK:
        try:
            from langchain_aws import ChatBedrockConverse
            from botocore.config import Config
            import boto3

            # Config expects "Claude-4"
            creds = ensure_model_credentials("Claude-4")

            # 创建带代理的 boto3 配置
            config = Config(
                region_name=creds['region_name']
            )
            # 创建 bedrock 客户端
            bedrock_client = boto3.client(
                service_name="bedrock-runtime",
                region_name=creds['region_name'],
                config=config
            )
            llm = ChatBedrockConverse(
                client=bedrock_client,
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                region_name=creds['region_name'],
                additional_model_request_fields={
                    "thinking": {"type": "enabled", "budget_tokens": 4096},
                }
            )
            return llm
        except ImportError:
            print("❌ 缺少 langchain_aws 依赖，请安装: pip install langchain-aws")
            raise
        except Exception as e:
            print(f"❌ Claude-4 初始化失败: {str(e)}")
            raise

    elif provider == ModelProvider.XAI:
        from langchain_xai import ChatXAI
        creds = ensure_model_credentials("Grok-4.1-Fast")
        llm = ChatXAI(
            api_key=creds["api_key"],
            model="grok-4-1-fast-reasoning",
        )
        return llm

    elif provider == ModelProvider.VERTEX_AI:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from google.oauth2 import service_account

            creds = ensure_model_credentials(model_type.value)
            credentials = service_account.Credentials.from_service_account_file(
                creds['credentials_path'],
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            # 仅构建客户端，不做网络验证
            llm = ChatGoogleGenerativeAI(
                credentials=credentials,
                model=get_gemini_model_name(model_type),
                project=creds["project"],
                location="global",  # gemini-3 只有全球节点
                vertex_ai=True,
                include_thoughts=True,
            )
            return llm
        except Exception as e:
            print(f"❌ Gemini 初始化失败: {str(e)}")
            raise

    elif provider == ModelProvider.LITELLM:
        try:
            # 延迟导入重依赖
            from langchain_openai import ChatOpenAI
            # 读取 OpenAI 密钥 (Config expects "LiteLLM")
            creds = ensure_model_credentials("LiteLLM")
            model_config = {
                "base_url": creds['base_url'],
                "api_key": creds["api_key"],
                "model": model_type.value
            }

            llm = ChatOpenAI(**model_config)
            return llm
        except ImportError:
            print("❌ 缺少 langchain_openai 依赖，请安装: pip install langchain-openai")
            raise

    elif provider == ModelProvider.OPENAI:
        try:
            # 延迟导入重依赖
            from langchain_openai import ChatOpenAI
            import httpx

            # 配置代理
            proxies = {
                "http://": "socks5://us1-proxy.owll.ai:11800",
                "https://": "socks5://us1-proxy.owll.ai:11800",
            }
            # 使用 httpx.Client
            http_client = httpx.Client(proxy=proxies["https://"])

            # 读取 OpenAI 密钥
            creds = ensure_model_credentials("gpt-5.2")
            os.environ["OPENAI_API_KEY"] = creds["api_key"]
            model_config = {
                "api_key": creds["api_key"],
                "http_client": http_client,
                "model": "gpt-5.2"
            }

            llm = ChatOpenAI(**model_config)
            return llm
        except ImportError:
            print("❌ 缺少 langchain_openai 依赖，请安装: pip install langchain-openai")
            raise

    elif provider == ModelProvider.DEEPSEEK:
        try:
            from langchain_deepseek import ChatDeepSeek
            creds = ensure_model_credentials(model_type.value)
            llm = ChatDeepSeek(
                model=model_type.value,  # deepseek-chat or deepseek-reasoner
                api_key=creds["api_key"]
            )
            return llm
        except ImportError:
            print("❌ 缺少 langchain_deepseek 依赖，请安装: pip install langchain-deepseek")
            raise

    elif provider == ModelProvider.ZHIPU:
        try:
            from langchain_openai import ChatOpenAI
            # 读取 OpenAI 密钥 (Config expects "LiteLLM")
            creds = ensure_model_credentials(ModelProvider.ZHIPU.value)
            model_config = {
                "base_url": creds['base_url'],
                "api_key": creds["api_key"],
                "model": model_type.value,
                "extra_body": {
                    "thinking": {
                        "type": "enabled"
                    }
                }
            }
            llm = ChatOpenAI(**model_config)
            return llm
        except ImportError:
            print("❌ 缺少 GLM 依赖")
            raise

    elif provider == ModelProvider.ALIBABA_CLOUD:
        try:
            from langchain_qwq import ChatQwen
            creds = ensure_model_credentials("qwen3-max")
            llm = ChatQwen(
                model="qwen3-max-2026-01-23",
                api_key=creds["api_key"],
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                enable_thinking=True,
                thinking_budget=2048,
            )
            return llm
        except ImportError:
            print("❌ 缺少 GLM 依赖")
            raise

    elif provider == ModelProvider.MOONSHOT:
        try:
            from langchain_openai import ChatOpenAI
            creds = ensure_model_credentials("Kimi 2.5")
            print(f"creds={creds}")
            llm = ChatOpenAI(
                api_key=creds["api_key"],
                model="kimi-k2-thinking",
                base_url="https://api.moonshot.cn/v1",
                max_retries=1
            )
            return llm
        except ImportError:
            print("❌ 缺少 langchain_openai 依赖")
            raise

    else:
        raise ValueError(f"不支持的模型厂商: {provider}")
