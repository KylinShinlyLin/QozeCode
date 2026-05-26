#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会话 checkpoint 管理器
过滤消息、构造 prompt、调用 LLM 生成结构化摘要、保存到文件

典型用法:
    from utils.checkpoint_manager import CheckpointManager
    mgr = CheckpointManager()
    filtered = mgr.filter_messages(state["messages"])
    prompt = mgr.build_checkpoint_prompt(filtered, "gpt-4", 50000, [], "无", 10)
    summary = await mgr.summarize(llm, prompt)
    filepath = mgr.save(summary)
"""
import os
import logging
from datetime import datetime

from langchain_core.messages import (
    HumanMessage, AIMessage, ToolMessage, SystemMessage, BaseMessage
)
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


class CheckpointManager:
    """管理会话 checkpoint 的保存"""

    # 使用绝对路径避免 cwd 变化导致写入位置异常
    CHECKPOINT_DIR = os.path.abspath(".qoze/memory")
    # 每条消息最大保留字符数，预留足够空间保留代码片段和命令输出
    MAX_CONTENT_LENGTH = 16000

    def __init__(self):
        os.makedirs(self.CHECKPOINT_DIR, exist_ok=True)

    def filter_messages(self, messages: list) -> list[dict]:
        """
        过滤消息列表：
        - 丢弃 SystemMessage
        - 保留 ToolMessage（包含工具调用结果，是关键上下文）
        - 丢弃 AIMessage 中的 thinking/reasoning_content
        - 保留 AIMessage 中纯 tool_calls 的消息（标注为工具调用）
        - 保留 HumanMessage.content 和 AIMessage.content
        - 超长消息截断
        返回: [{"role": "user"|"assistant"|"tool", "content": "...", "tool_name": "..."}, ...]
        """
        filtered: list[dict] = []
        for msg in messages:
            role = None
            content = None
            tool_name = None

            if isinstance(msg, HumanMessage):
                role = "user"
                content = self._extract_text_content(msg)
            elif isinstance(msg, AIMessage):
                role = "assistant"
                content = self._extract_text_content(msg)
                # 如果有 tool_calls，记录工具调用信息
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_names = [tc.get("name", "unknown") for tc in msg.tool_calls]
                    tool_name = ", ".join(tool_names)
            elif isinstance(msg, ToolMessage):
                role = "tool"
                content = self._extract_text_content(msg)
                tool_name = getattr(msg, "name", "unknown")
            elif isinstance(msg, SystemMessage):
                continue  # 丢弃 system prompt
            else:
                continue

            if content and content.strip():
                # 截断超长消息
                if len(content) > self.MAX_CONTENT_LENGTH:
                    content = content[:self.MAX_CONTENT_LENGTH] + (
                        "\n\n[... 内容过长，已截断 ...]"
                    )
                entry = {"role": role, "content": content}
                if tool_name:
                    entry["tool_name"] = tool_name
                filtered.append(entry)

        return filtered

    def _has_text_content(self, msg: BaseMessage) -> bool:
        """判断 AIMessage 是否有文字内容 (不是纯 tool_calls)"""
        content = msg.content
        if isinstance(content, str):
            return bool(content.strip())
        elif isinstance(content, list):
            return any(
                isinstance(p, dict) and p.get("type") == "text" and p.get("text", "").strip()
                for p in content
            )
        return False

    def _extract_text_content(self, msg: BaseMessage) -> str:
        """从 LangChain Message 中提取纯文本 (不含 thinking)"""
        content = msg.content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # 多模态消息，只取 text 类型的 part
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(p.get("text", ""))
            return " ".join(parts)
        return ""

    def build_checkpoint_prompt(
        self,
        filtered_messages: list[dict],
        model_name: str,
        token_count: int,
        active_skills: list[str],
        plan_status: str,
        conversation_rounds: int,
    ) -> str:
        """构造给 LLM 的 checkpoint 摘要 prompt（详细版，可恢复上下文）"""
        dialog_lines = []
        user_idx = 0
        for m in filtered_messages:
            if m["role"] == "user":
                user_idx += 1
                dialog_lines.append(f"### 👤 用户 (第 {user_idx} 轮)\n{m['content']}")
            elif m["role"] == "assistant":
                tool_info = f" [调用了工具: {m['tool_name']}]" if m.get("tool_name") else ""
                dialog_lines.append(f"### 🤖 AI{tool_info}\n{m['content']}")
            elif m["role"] == "tool":
                tool_name = m.get("tool_name", "unknown")
                dialog_lines.append(f"### 🔧 工具返回 ({tool_name})\n{m['content']}")

        dialog_text = "\n\n".join(dialog_lines)

        skills_text = ", ".join(active_skills) if active_skills else "无"

        prompt = f"""你是一个专业的会话归档专家。你需要将以下对话历史整理为一份**详细、可恢复**的 checkpoint 文档。

⚠️ 目标：当用户清理会话后，仅凭这份文档就能无缝继续之前的工作，不会丢失任何关键上下文。

---

## 输出格式要求

你必须输出纯 Markdown 文本，严格按照以下章节结构：

---

### 📋 当前任务上下文

详细描述：
- **正在做什么**: 当前任务的目标和范围（2-5 句话）
- **做到了哪一步**: 具体进度，已完成的部分和当前卡点
- **下一步计划**: 接下来要做什么（列出 1-3 个具体步骤）
- **关联计划**: 如果在执行某个 plan，标注当前是第几个任务、进度如何
- **阻塞项**: 是否有等待用户决策或外部条件的问题

---

### 🔑 关键决策与结论

对话中确定的所有重要决策、技术方案选择、设计决定。每条用 `-` 开头，包含：
- 做了什么决策
- 为什么做这个决策（简要理由）
- 如果有替代方案被否决，也记录下来

---

### 📁 文件变更记录

列出对话中涉及的所有文件操作：
- **创建**: 新建了哪些文件，文件用途
- **修改**: 修改了哪些文件，改了什么（关键代码片段或改动描述）
- **删除**: 删除了哪些文件
- **当前项目状态**: 用一句话描述项目当前处于什么状态

格式：`- 文件路径 — 操作描述（关键改动内容）`

---

### ⚡ 关键命令与操作

列出对话中执行的重要命令及其结果：
- 命令内容（如有敏感信息可脱敏）
- 执行结果（成功/失败/关键输出）
- 对项目产生的影响

---

### 💬 对话要点（详细版）

按时间线详细记录每轮对话的核心内容：
- **第 N 轮 - 用户**: 用户的完整请求和上下文
- **第 N 轮 - AI**: AI 做了什么操作、调用了什么工具、得出了什么结论
- **工具调用链**: 如果一轮中涉及多个工具调用，列出调用序列和关键结果

⚠️ 不要省略工具调用的实质内容——文件被修改了什么、命令执行了什么、搜索结果是什么，这些是恢复上下文的关键。

---

### 📝 待办事项

尚未完成的任务和下一步行动：
- 每个待办项一行，用 `- [ ]` 开头
- 标注优先级（高/中/低）
- 如果对话中没有明确的待办，写"无明确待办"

---

### 🏷️ 环境与状态快照

- 当前工作目录和项目
- 激活了哪些技能
- Git 分支状态（如有提及）
- 配置变更（如有）
- 其他重要的环境上下文

---

## 规则

1. **详细但不啰嗦**: 关键信息（文件路径、命令、代码片段、决策理由）必须保留，闲聊内容可概括
2. **保留实质操作**: 工具调用的内容和结果是最重要的上下文，不能省略
3. **可恢复性优先**: 假设读者完全不知道之前发生了什么，仅凭本文档就能继续工作
4. **每个章节都必须存在**: 即使内容为"无"，也要保留章节标题
5. **不要编造**: 严格基于对话历史，不要添加推测或建议
6. **代码片段**: 如果对话中涉及具体的代码修改，保留关键代码片段（不超过 30 行）
7. **Markdown 格式**: 保持清晰的可读性，合理使用标题、列表、代码块

---

## 会话元信息

- 模型: {model_name}
- 当前 token 用量: 约 {token_count}
- 激活技能: {skills_text}
- 计划状态: {plan_status}
- 对话轮次: {conversation_rounds} 轮

---

## 完整对话历史

{dialog_text}"""

        return prompt

    async def summarize(self, llm: BaseChatModel, prompt: str) -> str:
        """独立调用 LLM 生成 checkpoint 摘要 (无流式、无工具)"""
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            raw = response.content if hasattr(response, "content") else str(response)
            # 防御：部分模型 (如 deepseek-v4-pro) 的 content 可能是 list[dict]，需转为纯文本
            content = self._extract_text_content_str(raw)
            return content
        except Exception as e:
            logger.error(f"Checkpoint LLM summarization failed: {e}")
            raise RuntimeError(f"Checkpoint 摘要生成失败: {e}") from e

    @staticmethod
    def _extract_text_content_str(content) -> str:
        """从任意 content (str | list) 中提取纯文本字符串"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(p.get("text", ""))
            return " ".join(parts)
        return str(content) if content else ""

    def save(self, content: str) -> str:
        """保存 checkpoint 到 .qoze/memory/ 目录，返回文件路径"""
        timestamp = datetime.now().strftime("%H-%M-%S")
        filename = f"checkpoint-{timestamp}.md"
        filepath = os.path.join(self.CHECKPOINT_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except (IOError, OSError) as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise RuntimeError(f"Checkpoint 文件写入失败: {e}") from e
        return filepath
