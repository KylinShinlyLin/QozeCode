import os
import base64
from pathlib import Path

from langchain_core.tools import tool


def _get_image_mime_type(file_path: Path) -> str:
    """获取图片的 MIME 类型"""
    ext = file_path.suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return mime_types.get(ext, "image/png")


def _is_image_file(file_path: Path) -> bool:
    """检查文件是否为图片"""
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    return file_path.suffix.lower() in image_exts


def _encode_image_to_base64(file_path: Path) -> str:
    """将图片文件编码为 base64"""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


@tool
def load_image_file(file_path: str) -> str:
    """Load a single image file into the LLM context.
    
    Use this when you need to load a specific image that you know the path to.
    The image will be encoded and sent to the LLM for analysis.
    
    Args:
        file_path: Path to the image file (relative to cwd or absolute).
        
    Returns:
        JSON string with image data. The agent will convert this to multimodal message.
    """
    try:
        # 解析路径
        target = Path(file_path)
        if not target.is_absolute():
            target = (Path.cwd() / target).resolve()
        else:
            target = target.resolve()
        
        # 检查文件是否存在
        if not target.exists():
            return '[RUN_FAILED] {"error": "File not found"}'
        if not target.is_file():
            return '[RUN_FAILED] {"error": "Not a file"}'
        
        # 检查是否为图片
        if not _is_image_file(target):
            return '[RUN_FAILED] {"error": "Not an image file"}'
        
        # 获取相对路径（用于显示）
        try:
            rel_path = str(target.relative_to(Path.cwd()))
        except ValueError:
            rel_path = str(target.name)
        
        mime_type = _get_image_mime_type(target)
        
        import json
        result = {
            "_type": "image_single",
            "path": rel_path,
            "mime_type": mime_type,
        }
        return json.dumps(result, ensure_ascii=False)
            
    except Exception as e:
        return '[RUN_FAILED] {"error": "Failed to load image"}'
