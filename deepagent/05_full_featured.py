#!/usr/bin/env python3
"""
=== DeepAgents 05: 全功能 Agent ===
演示：组合多个中间件打造企业级 Agent
- FilesystemMiddleware: 管理上下文
- SubAgentMiddleware: 并行调度
- SummarizationMiddleware: 长对话压缩
- HumanInTheLoopMiddleware: 关键操作人工确认

这是 DeepAgents 最强大的用法 —— 把所有中间件组合起来。
"""
import os
from typing import Literal
from tavily import TavilyClient
from deepagents import create_deep_agent
from deepagents.middleware import (
    FilesystemMiddleware,
    SummarizationMiddleware,
)
from deepagents.middleware.filesystem import FilesystemPermission
from deepagents.middleware.subagents import SubAgent

# --- 工具定义 ---
tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY", ""))

def internet_search(
    query: str, max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
) -> dict:
    """搜索互联网获取最新信息"""
    return tavily.search(query, max_results=max_results, topic=topic)

# --- 子代理定义 ---
researcher = SubAgent(
    name="researcher",
    description="深度调研某个主题，返回结构化的研究报告。",
    system_prompt="你是专业研究员。进行多维度搜索，返回有引用的报告。",
    model="deepseek:deepseek-chat",
    tools=[internet_search],
)

writer = SubAgent(
    name="writer",
    description="将研究报告撰写为面向读者的文章。",
    system_prompt="你是技术作家。把研究报告转化为通俗易读的文章。",
    model="deepseek:deepseek-chat",
)

# --- 全功能 Agent ---
agent = create_deep_agent(
    model="deepseek:deepseek-chat",
    tools=[internet_search],
    subagents=[researcher, writer],
    middleware=[
        # 文件系统 —— Agent 可以写文件来管理长内容
        FilesystemMiddleware(
            permissions=FilesystemPermission(
                allowed_paths=["/tmp/deepagent_full"],
            ),
        ),
        # 摘要 —— 长对话自动压缩，防止上下文溢出
        SummarizationMiddleware(
            model="deepseek:deepseek-chat",
            # 当对话超过一定 token 数时自动触发摘要
            trigger=("tokens", 8000),
            keep=("messages", 10),  # 保留最近 10 条消息
        ),
    ],
    # 人机回环 —— 在执行写文件、搜索等操作前请求确认
    interrupt_on={
        "write_file": True,
        "internet_search": False,
    },
    system_prompt="""你是一个全能的 AI 工作助手，用中文交流。

你可以：
1. 🔍 使用 internet_search 搜索最新信息
2. 📁 使用文件系统读写文件（write_file, read_file, edit_file, ls）
3. 👥 分派 researcher 和 writer 子代理完成专业任务
4. 📝 长对话会自动摘要，不会丢失上下文

当处理复杂多步骤任务时，会自动规划为 todo list 逐步执行。
""",
)

# 执行演示任务
print("🚀 全功能 Agent 启动\n")
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": (
            "请帮我做一个关于 'Rust 在 AI 领域的应用现状' 的调研，"
            "把结果保存到 /tmp/deepagent_full/rust_ai_report.md"
        )
    }]
})

for msg in result["messages"]:
    if msg.type == "ai" and msg.content:
        print(f"\n{'='*60}")
        print(msg.content)
