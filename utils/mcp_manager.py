import os
import sys
import asyncio
from contextlib import AsyncExitStack
from typing import Any, List, Dict
import datetime

from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from pydantic import Field, create_model

def log(msg: str):
    """带时间戳的简易日志"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [MCP] {msg}", flush=True)

class McpManager:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.sessions: List[ClientSession] = []
        self._tools_cache: List[StructuredTool] = []

        # 定义要集成的 MCP 服务列表
        self.mcp_servers = [
            # Tavily 远程 SSE 服务
            {
                "name": "tavily",
                "type": "sse",
                "url": "https://mcp.tavily.com/mcp", # 基础 URL，Key 后续拼接
                "env_check": ["TAVILY_API_KEY"]
            },
            # Playwright 本地服务 (保留但注释掉，按需开启)
            # {
            #     "name": "playwright",
            #     "type": "stdio",
            #     "command": "npx",
            #     "args": ["-y", "@playwright/mcp@latest"]
            # }
        ]

    async def connect(self):
        """连接到所有配置的 MCP 服务"""
        log(f"正在启动 {len(self.mcp_servers)} 个 MCP 服务...")

        for server in self.mcp_servers:
            name = server["name"]
            server_type = server.get("type", "stdio")

            # 检查必要的环境变量
            if "env_check" in server:
                missing_envs = [key for key in server["env_check"] if key not in os.environ or not os.environ[key]]
                if missing_envs:
                    log(f"[{name}] ⚠️  启动跳过: 缺少必要环境变量 {', '.join(missing_envs)}")
                    log(f"[{name}] 请在终端执行 export {missing_envs[0]}='your_key' 后重试")
                    continue

            try:
                log(f"[{name}] 准备启动服务 (类型: {server_type})...")
                
                read_stream = None
                write_stream = None

                if server_type == "sse":
                    # SSE 连接逻辑
                    base_url = server["url"]
                    # 目前 Tavily MCP 需要通过 URL 参数传递 Key
                    # 格式: https://mcp.tavily.com/mcp/?tavilyApiKey=...
                    api_key = os.environ.get("TAVILY_API_KEY", "")
                    
                    # 确保 URL 格式正确
                    if "?" in base_url:
                         full_url = f"{base_url}&tavilyApiKey={api_key}"
                    else:
                         full_url = f"{base_url}?tavilyApiKey={api_key}"
                    
                    log(f"[{name}] 正在连接远程 SSE 端点...")
                    read_stream, write_stream = await self.exit_stack.enter_async_context(sse_client(full_url))
                    log(f"[{name}] SSE 连接建立成功")

                else:
                    # Stdio 连接逻辑 (默认)
                    log(f"[{name}] 执行命令: {server['command']} {' '.join(server['args'])}")
                    server_params = StdioServerParameters(
                        command=server["command"],
                        args=server["args"],
                        env=os.environ
                    )
                    log(f"[{name}] 正在建立 stdio 连接...")
                    read_stream, write_stream = await self.exit_stack.enter_async_context(stdio_client(server_params))
                    log(f"[{name}] stdio 连接建立成功")

                session = await self.exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
                log(f"[{name}] 正在初始化 Session...")

                await session.initialize()
                log(f"[{name}] Session 初始化完成！")

                self.sessions.append(session)
                log(f"[{name}] 服务连接完全就绪")

            except Exception as e:
                log(f"[{name}] ❌ 连接失败: {e}")
                import traceback
                traceback.print_exc()
                continue

    async def get_tools(self) -> List[StructuredTool]:
        """获取并转换所有 MCP 工具为 LangChain 工具"""
        if not self.sessions:
            log("没有活跃的 Session，尝试发起连接...")
            await self.connect()

        if not self.sessions:
            log("⚠️ 没有可用的 MCP Session，未加载任何外部工具。")
            return []

        self._tools_cache = []
        log(f"开始从 {len(self.sessions)} 个 Session 中获取工具...")

        for i, session in enumerate(self.sessions):
            try:
                log(f"正在从第 {i+1} 个 Session 获取工具定义...")
                result = await session.list_tools()
                mcp_tools = result.tools
                log(f"Session {i+1} 返回了 {len(mcp_tools)} 个工具")
                log(f"--- Session {i+1} 工具详情 ---")
                for t in mcp_tools:
                    log(f"  • {t.name}: {t.description[:100] if t.description else '无描述'}...")
                    props = list(t.inputSchema.get("properties", {}).keys())
                    log(f"    参数: {', '.join(props)}")
                log("---------------------------")

                for tool in mcp_tools:
                    fields = {}
                    for name, schema in tool.inputSchema.get("properties", {}).items():
                        description = schema.get("description", "")
                        if name in tool.inputSchema.get("required", []):
                            fields[name] = (Any, Field(description=description))
                        else:
                            fields[name] = (Any, Field(default=None, description=description))

                    args_model = create_model(f"{tool.name}_args", **fields)

                    async def _execute(
                            __tool_name=tool.name,
                            __session=session,
                            **kwargs
                    ) -> str:
                        try:
                            log(f"执行工具: {__tool_name} 参数: {kwargs}")
                            try:
                                # SSE 可能会慢一点，增加到 90s
                                result = await asyncio.wait_for(
                                    __session.call_tool(__tool_name, arguments=kwargs),
                                    timeout=90.0
                                )
                            except asyncio.TimeoutError:
                                return f"Error: Tool execution timed out after 90 seconds."

                            text_content = [c.text for c in result.content if c.type == "text"]
                            output = "\n".join(text_content)
                            log(f"工具 {__tool_name} 执行完成 (输出长度: {len(output)})")
                            return output
                        except Exception as e:
                            error_msg = f"Error executing {__tool_name}: {str(e)}"
                            log(f"❌ {error_msg}")
                            return error_msg

                    lang_tool = StructuredTool.from_function(
                        func=None,
                        coroutine=_execute,
                        name=tool.name,
                        description=tool.description[:1024] if tool.description else "No description",
                        args_schema=args_model
                    )
                    self._tools_cache.append(lang_tool)
            except Exception as e:
                log(f"❌ 获取工具列表失败: {e}")
                continue

        return self._tools_cache

    async def cleanup(self):
        if self.sessions:
            log("正在关闭所有 MCP 服务连接...")
            await self.exit_stack.aclose()
            self.sessions = []
            log("所有 MCP 服务已关闭")
