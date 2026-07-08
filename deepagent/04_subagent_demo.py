#!/usr/bin/env python3
"""
=== DeepAgents 04: 子代理调度 ===
演示：如何使用 SubAgentMiddleware 让父 Agent 分派任务给专业子代理

DeepAgents 的子代理系统：
1. 每个子代理有独立的上下文窗口（隔离）
2. 子代理可以有自己专属的工具和系统提示词
3. 父 Agent 自动决定何时分派、如何汇总结果
4. 支持并行分派多个子代理
"""
from deepagents import create_deep_agent
from deepagents.middleware.subagents import SubAgent

# 定义子代理 1: 代码审查专家
code_reviewer = SubAgent(
    name="code-reviewer",
    description="审查代码质量、安全性、性能。当需要 review 代码时调用。",
    system_prompt="""你是资深代码审查专家。收到代码后：
1. 检查代码风格和可读性  2. 检查潜在 bug 和安全漏洞
3. 检查性能问题  4. 给出改进建议（按严重程度排列）
输出格式：用 Markdown，分严重程度（🔴严重 🟡建议 🟢优化）""",
    model="deepseek:deepseek-chat",
)

# 定义子代理 2: 文档撰写专家
doc_writer = SubAgent(
    name="doc-writer",
    description="将技术内容转化为清晰易读的文档。当需要写文档时调用。",
    system_prompt="""你是技术文档专家。你会把技术描述转化为：
1. 面向初学者的友好文档  2. 包含代码示例  3. 有清晰的章节结构
输出格式：Markdown 文档，含目录、代码块、注意事项。""",
    model="deepseek:deepseek-chat",
)

# 创建父 Agent，注册子代理
agent = create_deep_agent(
    model="deepseek:deepseek-chat",
    subagents=[code_reviewer, doc_writer],
    system_prompt="""你是一个技术项目经理，用中文交流。

你有两个专业的子代理可以调用：
- code-reviewer: 审查代码
- doc-writer: 撰写文档

当用户给你代码或技术内容时，先交给子代理处理，再整合反馈给用户。
""",
)

# 演示：给一段代码让 Agent 审查 + 写文档
sample_code = """
def process_data(items):
    result = []
    for i in range(len(items)):
        item = items[i]
        if item['status'] == 'active':
            result.append(item)
    return result
"""

print("📋 提交代码给 Agent，让它用子代理审查和写文档...\n")
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": f"请帮我审查以下代码，然后写一份使用文档：\n```python\n{sample_code}\n```"
    }]
})

for msg in result["messages"]:
    if msg.type == "ai" and msg.content:
        print(f"🤖 {msg.content}")
