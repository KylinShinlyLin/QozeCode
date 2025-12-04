import asyncio
import os
from utils.mcp_manager import McpManager

# 设置用户的 Key
os.environ["TAVILY_API_KEY"] = "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"

async def main():
    print("开始测试 SSE MCP 连接...")
    manager = McpManager()
    try:
        tools = await manager.get_tools()
        print(f"获取到 {len(tools)} 个工具")
        
        # 尝试调用一下搜索
        if tools:
            search_tool = next((t for t in tools if "search" in t.name), None)
            if search_tool:
                print(f"测试调用工具: {search_tool.name}")
                # 使用简单参数，避免复杂参数报错
                res = await search_tool.ainvoke({"query": "Hello World", "max_results": 1})
                print(f"调用结果: {res[:100]}...")
            else:
                print("未找到 search 工具")
    except Exception as e:
        print(f"测试失败: {e}")
    finally:
        await manager.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
