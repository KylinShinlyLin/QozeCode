import os
import asyncio
from pathlib import Path

from langchain_core.tools import tool
from soniox import SonioxClient
from soniox.types import CreateTranscriptionConfig

import config_manager


# 支持的音频文件扩展名
SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".flac", ".ogg", ".opus",
    ".m4a", ".aac", ".wma", ".webm", ".mp4",
    ".aiff", ".aif", ".au", ".raw", ".pcm",
    ".amr", ".3gp", ".caf",
}


@tool
async def transcribe_audio(
    file_path: str,
    language_hints: list[str] | None = None,
) -> str:
    """使用 Soniox 语音识别将音频文件转写为文本。

    支持常见音频格式：WAV, MP3, FLAC, OGG, M4A, WebM, AAC 等。
    适用于会议录音、语音备忘录、播客等音频内容的文字转写。

    Args:
        file_path: 音频文件的本地路径（绝对路径或相对于当前工作目录的路径）
        language_hints: 语言提示列表（可选），帮助提高识别准确率。
                        ISO 639-1 两位语言代码，如 ["en"]（英语）, ["zh"]（中文）, ["en", "zh"]（中英混合）。
                        不传则自动检测语言。

    Returns:
        转写后的完整文本内容，或错误信息。
    """
    # 1. 参数校验
    file_path = file_path.strip()
    if not file_path:
        return "❌ 错误：请提供音频文件路径"

    audio_path = Path(file_path)
    if not audio_path.exists():
        return f"❌ 错误：文件不存在 —— {file_path}"

    if not audio_path.is_file():
        return f"❌ 错误：路径不是文件 —— {file_path}"

    suffix = audio_path.suffix.lower()
    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        return (
            f"❌ 错误：不支持的音频格式 '{suffix}'\n"
            f"支持的格式：{', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"
        )

    # 检查文件大小（Soniox 限制约 4GB，这里给个合理上限提示）
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 2000:
        return f"❌ 错误：文件过大 ({file_size_mb:.1f} MB)，请使用小于 2GB 的音频文件"

    # 2. 获取 API Key
    api_key = config_manager.get_soniox_key()
    if not api_key:
        return (
            "❌ 未检测到 Soniox API Key。\n"
            "请在 qoze.conf 的 [soniox] 节点下添加 api_key，例如：\n"
            "[soniox]\n"
            "api_key = your_soniox_api_key"
        )

    # 3. 调用 Soniox 进行转写
    try:
        # 构建配置
        config_kwargs = {}
        if language_hints:
            # 校验语言代码格式（2位小写字母）
            valid_hints = [h for h in language_hints if len(h) == 2 and h.isalpha()]
            if valid_hints:
                config_kwargs["language_hints"] = valid_hints

        config = CreateTranscriptionConfig(**config_kwargs) if config_kwargs else None

        client = SonioxClient(api_key=api_key)

        # 在线程池中执行同步阻塞操作，避免阻塞事件循环
        loop = asyncio.get_running_loop()

        def _do_transcribe():
            # 上传文件并等待转写完成
            transcription = client.stt.transcribe_and_wait(
                file=str(audio_path),
                filename=audio_path.name,
                config=config,
                wait_interval_sec=3.0,
            )

            # 获取转写结果文本
            transcript = client.stt.get_transcript(transcription.id)
            return transcript.text

        text = await loop.run_in_executor(None, _do_transcribe)

        if not text or not text.strip():
            return "⚠️ 转写完成，但未检测到语音内容（音频可能为静音或无有效语音）。"

        # 添加元信息
        result_parts = [
            f"# 音频转写结果\n",
            f"**文件**: {audio_path.name}",
            f"**大小**: {file_size_mb:.1f} MB",
        ]
        if language_hints:
            result_parts.append(f"**语言提示**: {', '.join(language_hints)}")
        result_parts.append(f"\n---\n\n{text}")

        return "\n".join(result_parts)

    except TimeoutError:
        return (
            f"❌ 转写超时：音频文件 {audio_path.name}（{file_size_mb:.1f} MB）转写时间过长，"
            f"请尝试使用较小的音频文件或检查网络连接。"
        )
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            return f"❌ Soniox API 认证失败，请检查 API Key 是否正确。\n详情：{error_msg}"
        return f"❌ 转写失败：{error_msg}"
