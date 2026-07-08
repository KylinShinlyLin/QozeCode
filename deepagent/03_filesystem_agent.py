#!/usr/bin/env python3
"""
=== DeepAgents 03: 文件系统 Agent ===
演示：使用 FilesystemMiddleware 让 Agent 在虚拟文件系统中
      读写文件、组织笔记、管理大量上下文

这是 DeepAgents 区别于 LangGraph 原生 Agent 的核心能力之一：
- Agent 可以把中间结果、长文档写入文件
- 避免上下文窗口溢出
- 支持 ls, read_file, write_file, edit_file 等操作
"""
from deepagents import create_deep_agent
from deepagents.middleware import FilesystemMiddleware
from deepagents.middleware.filesystem import FilesystemPermission

# 创建带文件系统中间件的 Agent
# FilesystemPermission 控制 Agent 可以访问哪些目录
agent = create_deep_agent(
    model="deepseek:deepseek-chat",
    # 添加文件系统中间件
    middleware=[
        FilesystemMiddleware(
            # 允许 Agent 读写的目录范围
            permissions=FilesystemPermission(
                allowed_paths=["/tmp/deepagent_workspace"],
                # 可以指定只读目录
                # read_only_paths=["/path/to/reference"],
            ),
        ),
    ],
    system_prompt="""你是一个编程助手，可以用中文交流。

你可以使用文件系统操作来管理信息：
- write_file: 将重要信息、分析结果保存为文件
- read_file: 读取之前保存的文件
- edit_file: 修改已有文件
- ls: 查看工作目录内容

当你需要处理大量信息时，善用文件系统来组织内容。
""",
)

# 演示：让 Agent 做一个分析并把结果写入文件
prompt = """请帮我分析 Python、JavaScript、Rust 三种语言的异步编程模型，
把分析结果写入 /tmp/deepagent_workspace/async_comparison.md 文件。
内容包括：各自的异步模型、语法对比、性能特点、适用场景。
"""
print(f"📝 任务: 分析异步编程模型并写入文件\n")

result = agent.invoke({
    "messages": [{"role": "user", "content": prompt}]
})

for msg in result["messages"]:
    if msg.type == "ai" and msg.content:
        print(f"🤖 {msg.content}")

# 检查生成的文件
import subprocess
r = subprocess.run(["cat", "/tmp/deepagent_workspace/async_comparison.md"], 
                   capture_output=True, text=True)
if r.returncode == 0:
    print(f"\n{'='*60}")
    print(f"📄 文件内容预览:\n{r.stdout[:1500]}")
