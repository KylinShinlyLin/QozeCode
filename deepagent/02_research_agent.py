#!/usr/bin/env python3
"""
=== DeepAgents 02: 研究 Agent（带任务规划） ===
演示：使用 TodoListMiddleware 让 Agent 自动分解任务
      使用 Tavily 搜索工具做网络调研
      
DeepAgents 的 create_deep_agent 默认自动启用 TodoListMiddleware！
Agent 会自动把复杂任务拆成步骤，逐步执行。
"""
import os
from typing import Literal
from tavily import TavilyClient
from deepagents import create_deep_agent

# 初始化 Tavily 搜索客户端（复用项目中已有的 Tavily Key）
tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY", ""))

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
) -> dict:
    """在互联网上搜索信息。用于查找最新资讯、文档、教程等。"""
    return tavily.search(query, max_results=max_results, topic=topic)

# 系统提示词
INSTRUCTIONS = """你是一个专业的研究分析师，用中文回答。你的工作流程：

1. 收到研究课题后，先规划需要调研的维度
2. 使用 internet_search 工具进行多轮搜索
3. 整合信息，撰写结构化的研究报告

研究报告格式：
- 📋 摘要（一句话）
- 🔍 关键发现（3-5 点）
- 📊 详细分析
- 💡 结论与建议
"""

# 创建研究 Agent（TodoListMiddleware 默认启用）
agent = create_deep_agent(
    model="deepseek:deepseek-chat",
    tools=[internet_search],
    system_prompt=INSTRUCTIONS,
)

# 执行研究任务
topic = "2025年AI Agent框架的发展趋势"
print(f"🔬 研究课题: {topic}\n")

result = agent.invoke({
    "messages": [{"role": "user", "content": f"请研究：{topic}"}]
})

for msg in result["messages"]:
    if msg.type == "ai" and msg.content:
        print(f"\n{'='*60}")
        print(msg.content)
