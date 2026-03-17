"""
Lark (飞书) 文档工具模块
提供读取、创建和修改 Lark 文档的能力

需要安装: pip install lark-oapi
需要在配置文件中配置 [Lark] 部分的 app_id 和 app_secret
"""

import re
import json
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, parse_qs
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# 尝试导入 lark-oapi
try:
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        import lark_oapi as lark
        from lark_oapi.api.docx.v1 import *
        from lark_oapi.api.drive.v1 import ListFileRequest

    LARK_SDK_AVAILABLE = True
except ImportError:
    LARK_SDK_AVAILABLE = False

from config_manager import _load_config


def _get_lark_credentials() -> Dict[str, str]:
    """从配置文件获取 Lark 凭证"""
    cfg, _ = _load_config()

    section = "Lark"
    if not cfg.has_section(section):
        raise RuntimeError(
            f"缺少 Lark 配置 (section [{section}]).\n"
            f"请在配置文件中添加:\n"
            f"[{section}]\n"
            f"app_id = your_app_id\n"
            f"app_secret = your_app_secret"
        )

    app_id = cfg.get(section, "app_id", fallback=None)
    app_secret = cfg.get(section, "app_secret", fallback=None)

    if not app_id or not app_secret:
        raise RuntimeError(
            f"Lark 配置不完整。需要 app_id 和 app_secret。\n"
            f"请在配置文件中添加:\n"
            f"[{section}]\n"
            f"app_id = your_app_id\n"
            f"app_secret = your_app_secret"
        )

    return {"app_id": app_id.strip("\"'"), "app_secret": app_secret.strip("\"'")}


def _create_lark_client() -> lark.Client:
    """创建 Lark API 客户端"""
    if not LARK_SDK_AVAILABLE:
        raise RuntimeError(
            "lark-oapi SDK 未安装。请运行: pip install lark-oapi"
        )

    creds = _get_lark_credentials()
    return lark.Client.builder() \
        .app_id(creds["app_id"]) \
        .app_secret(creds["app_secret"]) \
        .log_level(lark.LogLevel.INFO) \
        .build()


def _extract_doc_token_from_url(url: str) -> Optional[str]:
    """从 Lark 文档 URL 中提取文档 token"""
    patterns = [
        r'/(?:docx|wiki)/([a-zA-Z0-9]+)',
        r'/(?:docx|wiki)/([a-zA-Z0-9_\-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def _get_root_block_id(client: lark.Client, doc_token: str) -> Optional[str]:
    """获取文档的根块 ID (Page 块)"""
    try:
        request = ListDocumentBlockRequest.builder() \
            .document_id(doc_token) \
            .page_size(1) \
            .build()

        response = client.docx.v1.document_block.list(request)

        if response.success() and response.data and response.data.items:
            # 第一个块通常是 Page 块
            for block in response.data.items:
                block_type = getattr(block, 'block_type', 0)
                if block_type == 1:  # PAGE 块
                    return getattr(block, 'block_id', None)
            # 如果没有找到 Page 块，返回第一个块的 ID
            return getattr(response.data.items[0], 'block_id', None)

        # 如果列表为空，返回文档 ID 作为根块 ID
        return doc_token
    except Exception:
        return doc_token


def _create_text_element(content: str) -> Any:
    """创建文本元素"""
    # 限制单个文本元素长度，避免超长内容
    max_length = 5000
    if len(content) > max_length:
        content = content[:max_length] + "..."
    text_run = TextRunBuilder().content(content).build()
    return TextElementBuilder().text_run(text_run).build()


def _create_text_block(content: str) -> Block:
    """创建文本块"""
    text_element = _create_text_element(content)
    text = TextBuilder().elements([text_element]).build()
    return BlockBuilder().block_type(2).text(text).build()


def _create_heading_block(content: str, level: int = 1) -> Block:
    """创建标题块
    
    heading1-9 需要接收 Text 对象，而不是直接的元素列表
    """
    # 限制标题长度
    max_length = 500
    if len(content) > max_length:
        content = content[:max_length] + "..."

    text_element = _create_text_element(content)
    # heading 需要 Text 对象，包含 elements 字段
    heading_text = TextBuilder().elements([text_element]).build()

    builder = BlockBuilder().block_type(3)
    if level == 1:
        builder.heading1(heading_text)
    elif level == 2:
        builder.heading2(heading_text)
    elif level == 3:
        builder.heading3(heading_text)
    elif level == 4:
        builder.heading4(heading_text)
    elif level == 5:
        builder.heading5(heading_text)
    elif level == 6:
        builder.heading6(heading_text)
    elif level == 7:
        builder.heading7(heading_text)
    elif level == 8:
        builder.heading8(heading_text)
    else:
        builder.heading9(heading_text)

    return builder.build()


def _get_block_type_name(block_type: int) -> str:
    """获取块类型名称"""
    type_names = {
        1: "page",
        2: "text",
        3: "heading",
        4: "bullet",
        5: "ordered",
        6: "todo",
        7: "table",
        8: "table_cell",
        9: "quote",
        10: "quote_container",
        11: "callout",
        12: "divider",
        13: "image",
        14: "code",
        15: "file",
        16: "iframe",
        17: "sheet",
        18: "bitable",
        19: "chat_card",
        20: "diagram",
        21: "mindnote",
        22: "grid",
        23: "grid_column",
        24: "okr",
        25: "okr_objective",
        26: "okr_key_result",
        27: "okr_progress",
        28: "add_ons",
        29: "add_ons_embed",
        30: "jira_issue",
        31: "wiki_catalog",
        32: "view",
    }
    return type_names.get(block_type, f"unknown({block_type})")


def _get_block_info(block: Block) -> str:
    """获取块的详细信息用于调试"""
    try:
        block_type = getattr(block, 'block_type', 0)
        info = f"type={_get_block_type_name(block_type)}"

        if block_type == 2:  # text
            text = getattr(block, 'text', None)
            if text and hasattr(text, 'elements'):
                elements = text.elements
                if elements:
                    content = ""
                    for elem in elements[:1]:  # 只显示第一个元素
                        text_run = getattr(elem, 'text_run', None)
                        if text_run:
                            content = getattr(text_run, 'content', "")[:30]
                    info += f", content='{content}...'" if len(content) >= 30 else f", content='{content}'"

        elif block_type == 3:  # heading
            for i in range(1, 10):
                heading = getattr(block, f'heading{i}', None)
                if heading:
                    info += f", level={i}"
                    if hasattr(heading, 'elements') and heading.elements:
                        content = ""
                        for elem in heading.elements[:1]:
                            text_run = getattr(elem, 'text_run', None)
                            if text_run:
                                content = getattr(text_run, 'content', "")[:30]
                        info += f", title='{content}...'" if len(content) >= 30 else f", title='{content}'"
                    break

        return info
    except Exception as e:
        return f"error getting info: {str(e)}"


def _parse_markdown_to_blocks(content: str) -> List[Block]:
    """将 Markdown 解析为 Lark Block 对象列表
    
    优化策略：
    1. 合并连续的非标题行为一个文本块
    2. 限制单个块的内容长度
    """
    blocks = []
    lines = content.split('\n')

    # 用于累积普通文本行
    text_buffer = []

    def flush_text_buffer():
        """将缓冲的文本行刷新为一个文本块"""
        nonlocal text_buffer
        if text_buffer:
            # 合并多行文本
            combined_text = '\n'.join(text_buffer)
            # 限制长度
            max_text_length = 10000
            if len(combined_text) > max_text_length:
                # 如果太长，分成多个块
                for i in range(0, len(combined_text), max_text_length):
                    chunk = combined_text[i:i + max_text_length]
                    blocks.append(_create_text_block(chunk))
            else:
                blocks.append(_create_text_block(combined_text))
            text_buffer = []

    for line in lines:
        line = line.strip()
        if not line:
            # 空行也刷新缓冲区
            if text_buffer:
                text_buffer.append('')  # 保留空行
            continue

        # 处理标题
        if line.startswith('# '):
            flush_text_buffer()
            blocks.append(_create_heading_block(line[2:], level=1))
        elif line.startswith('## '):
            flush_text_buffer()
            blocks.append(_create_heading_block(line[3:], level=2))
        elif line.startswith('### '):
            flush_text_buffer()
            blocks.append(_create_heading_block(line[4:], level=3))
        elif line.startswith('#### '):
            flush_text_buffer()
            blocks.append(_create_heading_block(line[5:], level=4))
        elif line.startswith('##### '):
            flush_text_buffer()
            blocks.append(_create_heading_block(line[6:], level=5))
        elif line.startswith('###### '):
            flush_text_buffer()
            blocks.append(_create_heading_block(line[7:], level=6))
        else:
            # 普通文本行，添加到缓冲区
            text_buffer.append(line)

    # 刷新剩余的文本
    flush_text_buffer()

    return blocks


def _parse_blocks_to_markdown(blocks: List[Any]) -> str:
    """将 Lark 文档块解析为 Markdown 格式"""
    markdown_lines = []

    for block in blocks:
        if not block:
            continue

        block_type = getattr(block, 'block_type', 0)

        # Page: 文档标题
        if block_type == 1:  # PAGE
            page = getattr(block, 'page', None)
            if page:
                elements = _parse_text_elements(getattr(page, 'elements', []))
                if elements:
                    markdown_lines.append(f"# {elements}")
                    markdown_lines.append("")

        # Text: 普通文本
        elif block_type == 2:  # TEXT
            text = getattr(block, 'text', None)
            if text:
                elements = _parse_text_elements(getattr(text, 'elements', []))
                style = getattr(text, 'style', None)

                if style:
                    if getattr(style, 'bold', False):
                        elements = f"**{elements}**"
                    if getattr(style, 'italic', False):
                        elements = f"*{elements}*"
                    if getattr(style, 'strikethrough', False):
                        elements = f"~~{elements}~~"
                    if getattr(style, 'code', False):
                        elements = f"`{elements}`"

                markdown_lines.append(elements)

        # Heading: 标题
        elif block_type == 3:  # HEADING
            for i in range(1, 10):
                heading = getattr(block, f'heading{i}', None)
                if heading:
                    # heading 是 Text 对象，包含 elements 属性
                    heading_elements = getattr(heading, 'elements', [])
                    elements = _parse_text_elements(heading_elements)
                    markdown_lines.append(f"{'#' * i} {elements}")
                    markdown_lines.append("")
                    break

        # Code: 代码块
        elif block_type == 14:  # CODE
            code = getattr(block, 'code', None)
            if code:
                language = getattr(code, 'language', "")
                elements = _parse_text_elements(getattr(code, 'elements', []))
                markdown_lines.append(f"```{language}")
                markdown_lines.append(elements)
                markdown_lines.append("```")
                markdown_lines.append("")

        # Quote: 引用
        elif block_type == 4:  # QUOTE
            quote = getattr(block, 'quote', None)
            if quote:
                elements = _parse_text_elements(getattr(quote, 'elements', []))
                markdown_lines.append(f"> {elements}")
                markdown_lines.append("")

        # Divider: 分隔线
        elif block_type == 5:  # DIVIDER
            markdown_lines.append("---")
            markdown_lines.append("")

        # Image: 图片
        elif block_type == 27:  # IMAGE
            image = getattr(block, 'image', None)
            if image:
                token = getattr(image, 'token', "")
                markdown_lines.append(f"![image]({token})")
                markdown_lines.append("")

        # Table: 表格
        elif block_type == 12:  # TABLE
            markdown_lines.append("[表格内容]")
            markdown_lines.append("")

    return "\n".join(markdown_lines)


def _parse_text_elements(elements: List[Any]) -> str:
    """解析文本元素"""
    if not elements:
        return ""

    text_parts = []
    for elem in elements:
        if not elem:
            continue
        text_run = getattr(elem, 'text_run', None)
        if text_run:
            content = getattr(text_run, 'content', "")
            text_parts.append(content)
    return "".join(text_parts)


class ReadLarkDocumentInput(BaseModel):
    url: str = Field(..., description="Lark 文档的 URL，例如: https://xxx.larksuite.com/docx/AbCdEfGh")
    max_blocks: int = Field(default=-1, description="最多读取的块数量，-1 表示不限制，默认 -1")


@tool(args_schema=ReadLarkDocumentInput)
def read_lark_document(url: str, max_blocks: int = -1) -> str:
    """读取 Lark (飞书) 文档的内容。"""
    try:
        doc_token = _extract_doc_token_from_url(url)
        if not doc_token:
            return f"[RUN_FAILED] ❌ 无法从 URL 提取文档 token。\n{url}"

        client = _create_lark_client()

        # 获取文档元数据
        request = GetDocumentRequest.builder() \
            .document_id(doc_token) \
            .build()

        response = client.docx.v1.document.get(request)

        if not response.success():
            return f"[RUN_FAILED] ❌ 获取文档失败: {response.msg} (code: {response.code})"

        document = response.data.document
        title = getattr(document, 'title', "无标题") if document else "无标题"

        # 获取文档内容块
        all_blocks = []
        page_token = None

        while max_blocks == -1 or len(all_blocks) < max_blocks:
            builder = ListDocumentBlockRequest.builder() \
                .document_id(doc_token) \
                .page_size(500)

            if page_token:
                builder.page_token(page_token)

            block_request = builder.build()
            block_response = client.docx.v1.document_block.list(block_request)

            if not block_response.success():
                break

            items = block_response.data.items if block_response.data and hasattr(block_response.data, 'items') else []
            if items:
                all_blocks.extend(items)

            page_token = getattr(block_response.data, 'page_token', None) if block_response.data else None
            if not page_token or not items:
                break

        markdown_content = _parse_blocks_to_markdown(all_blocks)

        return f"""# 📄 Lark 文档: {title}

**文档 URL**: {url}
**文档 Token**: {doc_token}
**读取块数**: {len(all_blocks)}

---

{markdown_content}
"""

    except RuntimeError as e:
        return f"[RUN_FAILED] ❌ {str(e)}"
    except Exception as e:
        return f"[RUN_FAILED] ❌ 读取文档时出错: {str(e)}"


__all__ = [
    "read_lark_document",
]
