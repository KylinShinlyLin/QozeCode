#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会话 checkpoint 管理器
过滤消息、构造 prompt、调用 LLM 生成结构化摘要、保存到文件
"""
import os
from datetime import datetime
from typing import List, Optional

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage


class CheckpointManager:
    """管理会话 checkpoint 的保存"""

    CHECKPOINT_DIR = ".qoze/memory"
    MAX_CONTENT_LENGTH = 8000  # 每条消息最大保留字符数

    def __init__(self):
        os.makedirs(self.CHECKPOINT_DIR, exist_ok=True)

    def filter_messages(self, messages: list) -> list:
        """
        过滤消息列表：
        - 丢弃 SystemMessage、ToolMessage
        - 丢弃 AIMessage 中的 thinking/reasoning_content
        - 丢弃 AIMessage 中纯 tool_calls 的消息
        - 保留 HumanMessage.content 和 AIMessage.content (纯文字)
        - 超长消息截断
        返回: [{"role": "user"|"assistant", "content": "..."}, ...]
        """
        filtered = []
        for msg in messages:
            role = None
            content = None

            if isinstance(msg, HumanMessage):
                role = "user"
                content = self._extract_text_content(msg)
            elif isinstance(msg, AIMessage):
                # 如果 AIMessage 只有 tool_calls 没有文字，跳过
                if not self._has_text_content(msg):
                    continue
                role = "assistant"
                content = self._extract_text_content(msg)
            elif isinstance(msg, ToolMessage):
                continue  # 丢弃工具输出
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
                filtered.append({"role": role, "content": content})

        return filtered

    def _has_text_content(self, msg) -> bool:
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

    def _extract_text_content(self, msg) -> str:
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
        filtered_messages: list,
        model_name: str,
        token_count: int,
        active_skills: list,
        plan_status: str,
        conversation_rounds: int,
    ) -> str:
        """构造给 LLM 的 checkpoint 摘要 prompt"""
        dialog_lines = []
        for i, m in enumerate(filtered_messages):
            if m["role"] == "user":
                dialog_lines.append(f"### 用户 (第 {i + 1} 条)\n{m['content']}")
            else:
                dialog_lines.append(f"### AI\n{m['content']}")

        dialog_text = "\n\n".join(dialog_lines)

        skills_text = ", ".join(active_skills) if active_skills else "无"

        prompt = f"""你是一个专业的会话摘要专家。请将以下对话历史整理为一份结构化的 checkpoint 文档。

## 输出格式要求

你必须输出纯 Markdown 文本，包含以下章节：

### 当前任务上下文
正在做什么工作、做到了哪一步、下一步计划做什么。
如果在执行某个计划 (plan)，标注当前任务进度。

### 关键决策与结论
对话中确定的重要决策、技术方案选择、设计决定。每条一行，用 - 开头。

### 对话要点
按时间线列出每轮对话的核心内容。格式：
- **用户**: [一句话概括用户请求]
- **AI**: [一句话概括 AI 做了什么/回答了什么]

### 待办事项
尚未完成的任务和下一步行动。如果对话中没有明确的待办，写"无"。

## 规则
- 简洁准确，不要编造对话中不存在的内容
- 不要提及 thinking 过程或工具调用细节
- 每个章节都必须存在，即使内容为"无"
- 不要添加任何对话历史之外的建议或分析

---

## 会话元信息
- 模型: {model_name}
- 当前 token 用量: 约 {token_count}
- 激活技能: {skills_text}
- 计划状态: {plan_status}
- 对话轮次: {conversation_rounds} 轮

---

## 对话历史

{dialog_text}"""

        return prompt

    async def summarize(self, llm, prompt: str) -> str:
        """独立调用 LLM 生成 checkpoint 摘要 (无流式、无工具)"""
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content if hasattr(response, "content") else str(response)

    def save(self, content: str) -> str:
        """保存 checkpoint 到 .qoze/memory/ 目录，返回文件路径"""
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        filename = f"checkpoint-{timestamp}.md"
        filepath = os.path.join(self.CHECKPOINT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath
