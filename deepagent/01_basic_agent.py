#!/usr/bin/env python3
"""
=== DeepAgents 01: 最简 Agent（流式 + 状态提示版） ===
演示：create_deep_agent 的流式用法，带实时状态切换
- stream_mode="messages" — token 级流式 + 知道当前在哪个节点
- 动态展示：💭思考中 / 🔧调用工具 / 🤖回复中
"""
from deepagents import create_deep_agent


def get_weather(city: str) -> str:
    """查询指定城市的天气"""
    weather_data = {
        "北京": "晴，25°C", "上海": "多云，28°C", "深圳": "阵雨，30°C",
        "东京": "晴，22°C", "纽约": "阴，15°C",
    }
    return weather_data.get(city, f"找不到 {city} 的天气数据")


agent = create_deep_agent(
    model="deepseek:deepseek-v4-pro",
    tools=[get_weather],
    system_prompt="你是一个乐于助人的助手，用中文回答。",
)

print("=" * 60)
print("🚀 Agent 开始运行（流式 + 状态提示）")
print("=" * 60)

current_node = None       # 跟踪当前节点，切换状态
tool_calls_shown = set()  # 避免重复打印工具调用信息

# stream_mode="messages" → yield (message_chunk, metadata)
for chunk, metadata in agent.stream(
    {"messages": [{"role": "user", "content": "北京和深圳今天天气怎么样？"}]},
    stream_mode="messages",
):
    node = metadata.get("langgraph_node", "")

    # --- 节点切换 → 打印状态横幅 ---
    if node != current_node:
        current_node = node
        if node == "agent":
            print("\n💭 [思考中...]")
        elif node == "tools":
            print("\n🔧 [执行工具中...]")

    # --- 工具调用出现时 ---
    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
        for tc in chunk.tool_calls:
            if tc.get("name") and tc["name"] not in tool_calls_shown:
                tool_calls_shown.add(tc["name"])
                print(f"   📞 调用: {tc['name']}({tc.get('args', {})})")

    # --- 工具返回结果 ---
    if chunk.type == "tool" and chunk.content:
        content = str(chunk.content)
        display = content[:100] + "..." if len(content) > 100 else content
        print(f"   ✅ 结果: {display}")
        tool_calls_shown.clear()

    # --- AI 文本回复（逐 token 流式输出） ---
    if chunk.type == "AIMessageChunk" and chunk.content:
        # 第一次出现文本时换行
        if not hasattr(chunk, "_text_started"):
            chunk._text_started = True
        print(chunk.content, end="")

print("\n\n" + "=" * 60)
print("✅ 完成")
