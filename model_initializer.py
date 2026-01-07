"""
模型初始化模块
负责根据模型名称初始化对应的LLM实例
"""

import os

# 屏蔽 absl 库的 STDERR 警告
os.environ.setdefault('ABSL_LOGGING_VERBOSITY', '1')  # 只显示 WARNING 及以上级别
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')  # 屏蔽 TensorFlow 信息和警告

# 保留轻量级导入
from shared_console import console


def get_gemini_model_name(model_name):
    if model_name == 'gemini-3-pro':
        return "gemini-3-pro-preview"
    elif model_name == 'gemini-3-flash':
        return "gemini-3-flash-preview"
    return None


def initialize_llm(model_name: str):
    """根据模型名称初始化对应的LLM"""
    import os
    from config_manager import ensure_model_credentials
    if model_name == 'claude-4':
        try:
            # 延迟导入重依赖
            from langchain_aws import ChatBedrock
            from botocore.config import Config
            import boto3

            # 读取 AWS 凭证（不做网络验证）
            creds = ensure_model_credentials(model_name)

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

            llm = ChatBedrock(
                client=bedrock_client,
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                region_name=creds['region_name']
            )
            return llm
        except ImportError:
            print("❌ 缺少 langchain_aws 依赖，请安装: pip install langchain-aws")
            raise
        except Exception as e:
            print(f"❌ Claude-4 初始化失败: {str(e)}")
            raise
    elif model_name in ('gemini-3-pro', 'gemini-3-flash'):
        try:
            from langchain_google_vertexai import ChatVertexAI
            from google.oauth2 import service_account
            import os
            import logging
            import warnings

            # 抑制 Gemini schema 相关的警告信息
            logging.getLogger('langchain_google_vertexai').setLevel(logging.ERROR)
            logging.getLogger('google.ai.generativelanguage_v1beta').setLevel(logging.ERROR)
            # 抑制 vertex_ai 参数警告
            warnings.filterwarnings("ignore", message=".*vertex_ai.*not default parameter.*")
            creds = ensure_model_credentials(model_name)
            credentials = service_account.Credentials.from_service_account_file(
                creds['credentials_path'],
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            # 仅构建客户端，不做网络验证
            llm = ChatVertexAI(
                credentials=credentials,
                model_name=get_gemini_model_name(model_name),
                project=creds["project"],
                location="global",  # gemini-3 只有全球节点
                vertex_ai=True,
                include_thoughts=True,
            )
            return llm
        except Exception as e:
            print(f"❌ Gemini 初始化失败: {str(e)}")
            raise
    elif model_name in ('gpt-5.1', 'gpt-5.2', 'gpt-5-codex'):
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
            creds = ensure_model_credentials(model_name)
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
        except Exception as e:
            print(f"❌ {model_name} 初始化失败: {str(e)}")
            raise
    elif model_name == 'deepseek-reasoner':
        try:
            # 延迟导入重依赖
            from langchain_deepseek import ChatDeepSeek
            # 读取 DeepSeek 密钥
            creds = ensure_model_credentials(model_name)

            llm = ChatDeepSeek(
                model="deepseek-chat",
                api_key=creds["api_key"]
            )
            return llm
        except ImportError:
            print("❌ 缺少 langchain_deepseek 依赖，请安装: pip install langchain-deepseek")
            raise
        except Exception as e:
            print(f"❌ DeepSeek 初始化失败: {str(e)}")
            raise
    elif model_name == 'glm-4.6':
        try:
            # 延迟导入重依赖
            from langchain_community.chat_models import ChatZhipuAI

            # 读取 DeepSeek 密钥
            creds = ensure_model_credentials(model_name)
            llm = ChatZhipuAI(
                model="GLM-4.6",
                api_key=creds["api_key"],
                temperature=0.3,
                # thinking={"type": "enable"}
            )
            return llm
        except ImportError:
            print("❌ 缺少 GLM 依赖")
            raise
        except Exception as e:
            print(f"❌ GLM 初始化失败: {str(e)}")
            raise

    elif model_name == 'qwen3-max':
        try:
            # 延迟导入重依赖
            from langchain_qwq import ChatQwen

            # 读取 DeepSeek 密钥
            creds = ensure_model_credentials(model_name)
            llm = ChatQwen(
                model="qwen3-max-preview",
                # model="qwen3-max",
                temperature=0.3,
                api_key=creds["api_key"],
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                enable_thinking=True,
                thinking_budget=2048,
            )
            return llm
        except ImportError:
            print("❌ 缺少 GLM 依赖")
            raise
        except Exception as e:
            print(f"❌ GLM 初始化失败: {str(e)}")
            raise
    else:
        raise ValueError(f"不支持的模型: {model_name}")


def verify_credentials(model_name: str):
    """
    针对不同模型执行快速凭证验证（短超时，不在加载状态下）。
    成功则静默，失败抛异常。
    """
    import os
    import httpx
    from config_manager import ensure_model_credentials

    if model_name in ('gpt-5', 'gpt-5-codex'):
        creds = ensure_model_credentials(model_name)
        api_key = creds["api_key"]
        os.environ["OPENAI_API_KEY"] = api_key

    elif model_name == 'DeepSeek':
        creds = ensure_model_credentials(model_name)
        api_key = creds["api_key"]
        os.environ["DEEPSEEK_API_KEY"] = api_key
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(
                    "https://api.deepseek.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
            if r.status_code != 200:
                raise RuntimeError(f"DeepSeek 验证失败: {r.status_code} {r.text[:200]}")
        except Exception as e:
            raise RuntimeError(f"DeepSeek 验证失败: {e}")

    elif model_name == 'claude-4':
        import boto3
        from botocore.config import Config
        ensure_model_credentials(model_name)

    elif model_name == 'gemini':
        creds = ensure_model_credentials(model_name)
        cred_path = creds.get("credentials_path")
        if not cred_path or not os.path.exists(cred_path):
            raise RuntimeError("Gemini 凭证验证失败: 凭证文件不存在")

    else:
        raise ValueError(f"不支持的模型: {model_name}")


def verify_llm(llm):
    """
    对 LLM 做一次最小调用验证密钥是否可用。
    如果失败则抛出异常由上层处理。
    """
    try:
        # LangChain Chat 模型支持直接 invoke 字符串
        llm.invoke("ping")
    except Exception as e:
        console.print(f"❌ 密钥验证失败: {e}", style="red")
        raise
