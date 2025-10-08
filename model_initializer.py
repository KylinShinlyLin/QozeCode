"""
模型初始化模块
负责根据模型名称初始化对应的LLM实例
"""

import boto3
import httpx
from langchain_deepseek import ChatDeepSeek
from langchain_google_vertexai import ChatVertexAI


def initialize_llm(model_name: str):
    """根据模型名称初始化对应的LLM"""
    import os
    from shared_console import console
    from config_manager import ensure_model_credentials
    if model_name == 'claude-4':
        # 使用 Claude-4 (通过 Bedrock)
        try:
            from langchain_aws import ChatBedrock

            # 配置代理
            proxies = {
                "http://": "socks5://us1-proxy.owll.ai:11800",
                "https://": "socks5://us1-proxy.owll.ai:11800",
            }

            # 读取 AWS 凭证（不做网络验证）
            creds = ensure_model_credentials('claude-4')

            # 创建带代理的 boto3 配置
            from botocore.config import Config
            config = Config(
                proxies=proxies,
                region_name=creds['region_name']
            )

            # 创建 bedrock 客户端
            bedrock_client = boto3.client(
                'bedrock-runtime',
                aws_access_key_id=creds['aws_access_key_id'],
                aws_secret_access_key=creds['aws_secret_access_key'],
                region_name=creds['region_name'],
                config=config
            )

            llm = ChatBedrock(
                client=bedrock_client,
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            )
            return llm
        except ImportError:
            print("❌ 缺少 langchain_aws 依赖，请安装: pip install langchain-aws")
            raise
        except Exception as e:
            print(f"❌ Claude-4 初始化失败: {str(e)}")
            raise

    elif model_name == 'gemini':
        # 使用 Gemini
        try:
            # 读取 VertexAI 凭证（不做网络验证）
            creds = ensure_model_credentials('gemini')
            # 配置 Google 凭证路径
            if creds.get("credentials_path"):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds["credentials_path"]

            llm = ChatVertexAI(
                model_name="gemini-2.5-pro",
                project=creds["project"],
                location=creds["location"]
            )
            return llm
        except Exception as e:
            print(f"❌ Gemini 初始化失败: {str(e)}")
            raise

    elif model_name == 'gpt-5':
        # 使用 GPT-5 (通过 OpenAI)
        try:
            from langchain_openai import ChatOpenAI

            # 配置代理
            proxies = {
                "http://": "socks5://us1-proxy.owll.ai:11800",
                "https://": "socks5://us1-proxy.owll.ai:11800",
            }

            # 方法1: 使用 httpx.Client (推荐用于 langchain_openai)
            http_client = httpx.Client(proxy=proxies["https://"])

            # 读取 OpenAI 密钥（不做网络验证），并设置环境变量提高兼容性
            creds = ensure_model_credentials('gpt-5')
            os.environ["OPENAI_API_KEY"] = creds["api_key"]

            llm = ChatOpenAI(
                model="gpt-5",
                temperature=0.1,
                api_key=creds["api_key"],
                http_client=http_client,
                reasoning_effort="minimal"
            )
            return llm
        except ImportError:
            print("❌ 缺少 langchain_openai 依赖，请安装: pip install langchain-openai")
            raise
        except Exception as e:
            print(f"❌ GPT-5 初始化失败: {str(e)}")
            raise
    elif model_name == 'gpt-5-codex':
        # 使用 GPT-5 (通过 OpenAI)
        try:
            from langchain_openai import ChatOpenAI

            # 配置代理
            proxies = {
                "http://": "socks5://us1-proxy.owll.ai:11800",
                "https://": "socks5://us1-proxy.owll.ai:11800",
            }

            # 方法1: 使用 httpx.Client (推荐用于 langchain_openai)
            http_client = httpx.Client(proxy=proxies["https://"])

            # 读取 OpenAI 密钥（不做网络验证），并设置环境变量提高兼容性
            creds = ensure_model_credentials('gpt-5-codex')
            os.environ["OPENAI_API_KEY"] = creds["api_key"]

            llm = ChatOpenAI(
                model="gpt-5-codex",
                temperature=0.1,
                api_key=creds["api_key"],
                http_client=http_client,
            )
            return llm
        except ImportError:
            print("❌ 缺少 langchain_openai 依赖，请安装: pip install langchain-openai")
            raise
        except Exception as e:
            print(f"❌ GPT-5 初始化失败: {str(e)}")
            raise
    elif model_name == 'DeepSeek':
        # 使用 DeepSeek
        try:
            # 读取 DeepSeek 密钥（不做网络验证），并设置环境变量提高兼容性
            creds = ensure_model_credentials('DeepSeek')
            os.environ["DEEPSEEK_API_KEY"] = creds["api_key"]

            llm = ChatDeepSeek(
                model="deepseek-reasoner",
                api_key=creds["api_key"]
            )
            return llm
        except Exception as e:
            print(f"❌ DeepSeek 初始化失败: {str(e)}")
            raise


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
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
            if r.status_code != 200:
                raise RuntimeError(f"OpenAI 验证失败: {r.status_code} {r.text[:200]}")
        except Exception as e:
            raise RuntimeError(f"OpenAI 验证失败: {e}")

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
        creds = ensure_model_credentials(model_name)
        try:
            sts = boto3.client(
                "sts",
                aws_access_key_id=creds["aws_access_key_id"],
                aws_secret_access_key=creds["aws_secret_access_key"],
                region_name=creds["region_name"],
                config=Config(retries={"max_attempts": 3})
            )
            sts.get_caller_identity()
        except Exception as e:
            raise RuntimeError(f"AWS 凭证验证失败: {e}")

    elif model_name == 'gemini':
        creds = ensure_model_credentials(model_name)
        cred_path = creds.get("credentials_path")
        if not cred_path or not os.path.exists(cred_path):
            raise RuntimeError("Gemini 凭证验证失败: 凭证文件不存在")
        # 轻量验证到此为止，避免耗时的 API 调用

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
        from shared_console import console
        console.print(f"❌ 密钥验证失败: {e}", style="red")
        raise
