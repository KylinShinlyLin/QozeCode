#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode MCP (Model Context Protocol) Manager
基于 langchain-mcp-adapters 实现 MCP 服务器集成管理

设计理念：
- 与 SkillManager 保持一致的管理模式（发现、激活、反激活）
- 配置存储在 ~/.qoze/mcp/ 目录下，每个服务器一个 JSON 文件
- 支持 stdio 和 http 两种传输协议
- 激活时动态加载 MCP 工具到 Agent 的工具列表
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from shared_console import console
from rich.table import Table
from rich.panel import Panel


@dataclass
class MCPServerConfig:
    """MCP 服务器配置"""
    name: str
    transport: str  # "stdio" or "http"
    description: str = ""
    enabled: bool = False
    
    # stdio 传输参数
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    
    # http 传输参数
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    
    # 状态
    active: bool = False  # 当前是否激活
    tools_count: int = 0  # 提供的工具数量


class MCPManager:
    """MCP 管理器：发现、加载、管理 MCP 服务器"""

    def __init__(self):
        self.servers: Dict[str, MCPServerConfig] = {}
        self._client = None  # MultiServerMCPClient 实例（延迟初始化）
        self._active_tools: List = []  # 当前激活的 MCP 工具列表
        self._tools_by_name: Dict[str, any] = {}  # 工具名 -> 工具函数映射
        
        # MCP 配置目录
        self.config_dir = Path.home() / ".qoze" / "mcp"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 全局状态文件
        self.state_file = self.config_dir / "_state.json"
        
        # 加载配置
        self._load_state()
        self._discover_servers()

    # ==================== 配置发现 ====================

    def _discover_servers(self):
        """发现所有 MCP 服务器配置文件"""
        if not self.config_dir.exists():
            return

        for item in self.config_dir.iterdir():
            if item.is_file() and item.suffix == '.json' and not item.name.startswith('_'):
                try:
                    config = self._load_server_config(item)
                    if config and config.name not in self.servers:
                        self.servers[config.name] = config
                except Exception as e:
                    console.print(f"[yellow]⚠️ 加载 MCP 配置失败 {item.name}: {e}[/yellow]")

    def _load_server_config(self, filepath: Path) -> Optional[MCPServerConfig]:
        """加载单个 MCP 服务器配置文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            name = data.get("name")
            if not name:
                console.print(f"[yellow]⚠️ MCP 配置文件 {filepath.name} 缺少 'name' 字段[/yellow]")
                return None
            
            config = MCPServerConfig(
                name=name,
                transport=data.get("transport", "stdio"),
                description=data.get("description", ""),
                enabled=data.get("enabled", False),
                command=data.get("command"),
                args=data.get("args", []),
                env=data.get("env", {}),
                url=data.get("url"),
                headers=data.get("headers", {}),
            )
            
            return config
        except json.JSONDecodeError as e:
            console.print(f"[red]❌ MCP 配置文件 {filepath.name} JSON 格式错误: {e}[/red]")
            return None
        except Exception as e:
            console.print(f"[red]❌ 读取 MCP 配置文件 {filepath.name} 失败: {e}[/red]")
            return None

    # ==================== 状态持久化 ====================

    def _load_state(self):
        """加载全局状态（哪些服务器是激活的）"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                self._active_server_names = state.get('active_servers', [])
            except Exception:
                self._active_server_names = []
        else:
            self._active_server_names = []

    def _save_state(self):
        """保存全局状态"""
        try:
            state = {
                'active_servers': self._active_server_names
            }
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            console.print(f"[red]❌ 保存 MCP 状态失败: {e}[/red]")

    # ==================== MCP 客户端 ====================

    def _get_client(self):
        """获取或创建 MultiServerMCPClient 实例"""
        if self._client is None:
            try:
                from langchain_mcp_adapters.client import MultiServerMCPClient
                self._client = MultiServerMCPClient
            except ImportError:
                console.print("[red]❌ langchain-mcp-adapters 未安装，请运行: pip install langchain-mcp-adapters[/red]")
                return None
        return self._client

    def _build_client_config(self) -> dict:
        """构建 MultiServerMCPClient 所需的配置字典"""
        client_config = {}
        
        for name, server in self.servers.items():
            if not server.active:
                continue
            
            if server.transport == "stdio":
                if not server.command:
                    console.print(f"[yellow]⚠️ MCP 服务器 '{name}' 缺少 command 配置[/yellow]")
                    continue
                cfg = {
                    "transport": "stdio",
                    "command": server.command,
                    "args": server.args,
                }
                if server.env:
                    cfg["env"] = server.env
                client_config[name] = cfg
                
            elif server.transport in ("http", "streamable-http"):
                if not server.url:
                    console.print(f"[yellow]⚠️ MCP 服务器 '{name}' 缺少 url 配置[/yellow]")
                    continue
                cfg = {
                    "transport": server.transport,
                    "url": server.url,
                }
                if server.headers:
                    cfg["headers"] = server.headers
                client_config[name] = cfg
        
        return client_config

    async def load_tools(self) -> List:
        """
        异步加载所有激活 MCP 服务器的工具
        
        Returns:
            List: LangChain 工具列表
        """
        client_class = self._get_client()
        if client_class is None:
            return []
        
        client_config = self._build_client_config()
        if not client_config:
            self._active_tools = []
            self._tools_by_name = {}
            return []
        
        try:
            client = client_class(client_config)
            tools = await client.get_tools()
            
            self._active_tools = tools
            self._tools_by_name = {tool.name: tool for tool in tools}
            
            # 更新工具数量
            for name in client_config:
                # 统计每个服务器的工具
                server_tools = [t for t in tools if hasattr(t, 'metadata') and t.metadata and 
                               t.metadata.get('_mcp_server') == name]
                if name in self.servers:
                    self.servers[name].tools_count = len(server_tools)
            
            console.print(f"[green]✅ 已加载 {len(tools)} 个 MCP 工具[/green]")
            return tools
            
        except Exception as e:
            console.print(f"[red]❌ 加载 MCP 工具失败: {e}[/red]")
            import traceback
            traceback.print_exc()
            return []

    # ==================== 激活/反激活操作 ====================

    async def activate_server(self, server_name: str) -> Optional[MCPServerConfig]:
        """
        激活指定的 MCP 服务器
        
        Args:
            server_name: 服务器名称
            
        Returns:
            MCPServerConfig 或 None
        """
        # 刷新配置
        self._discover_servers()
        
        if server_name not in self.servers:
            console.print(f"[yellow]⚠️ MCP 服务器 '{server_name}' 不存在[/yellow]")
            return None
        
        server = self.servers[server_name]
        
        if server.active:
            console.print(f"[yellow]⚠️ MCP 服务器 '{server_name}' 已经激活[/yellow]")
            return server
        
        # 标记激活
        server.active = True
        if server_name not in self._active_server_names:
            self._active_server_names.append(server_name)
        self._save_state()
        
        # 重新加载所有工具
        await self.load_tools()
        
        console.print(f"[green]✅ MCP 服务器 '{server_name}' 已激活，提供 {server.tools_count} 个工具[/green]")
        return server

    async def deactivate_server(self, server_name: str) -> bool:
        """
        反激活指定的 MCP 服务器
        
        Args:
            server_name: 服务器名称
            
        Returns:
            bool: 是否成功
        """
        if server_name not in self.servers:
            console.print(f"[yellow]⚠️ MCP 服务器 '{server_name}' 不存在[/yellow]")
            return False
        
        server = self.servers[server_name]
        
        if not server.active:
            console.print(f"[yellow]⚠️ MCP 服务器 '{server_name}' 未激活[/yellow]")
            return False
        
        # 标记反激活
        server.active = False
        if server_name in self._active_server_names:
            self._active_server_names.remove(server_name)
        self._save_state()
        
        # 重新加载所有工具（移除该服务器的工具）
        await self.load_tools()
        
        console.print(f"[yellow]🔻 MCP 服务器 '{server_name}' 已反激活[/yellow]")
        return True

    # ==================== 查询接口 ====================

    def get_available_servers(self) -> Dict[str, str]:
        """获取所有可用的 MCP 服务器（名称 -> 描述）"""
        self._discover_servers()
        return {name: s.description for name, s in self.servers.items()}

    def get_active_servers(self) -> Dict[str, MCPServerConfig]:
        """获取当前激活的 MCP 服务器"""
        return {name: s for name, s in self.servers.items() if s.active}

    def get_active_tools(self) -> List:
        """获取当前激活的 MCP 工具列表"""
        return self._active_tools

    def get_tools_by_name(self) -> Dict[str, any]:
        """获取工具名 -> 工具映射"""
        return self._tools_by_name

    def get_mcp_context(self) -> str:
        """获取 MCP 上下文信息（用于注入系统提示词）
        展示所有可用的 MCP 服务器及其状态，类似 Skills 的展示方式。
        """
        self._discover_servers()
        available = self.get_available_servers()
        if not available:
            return ""

        active_names = set(self.get_active_servers().keys())
        lines = ["\n## 🔌 Available MCP Servers"]
        lines.append("MCP (Model Context Protocol) 服务器为 Agent 提供额外的外部工具。")
        lines.append("激活/反激活由用户在 TUI 侧边栏手动控制。")
        lines.append("")

        for name, desc in available.items():
            if name in active_names:
                server = self.servers[name]
                transport_info = f"stdio ({server.command})" if server.transport == "stdio" else f"http ({server.url})"
                lines.append(f"- 🟢 **{name}**: {desc} | transport: {transport_info} | tools: {server.tools_count}")
            else:
                lines.append(f"- ⚪ **{name}**: {desc}")

        # 列出激活的工具
        if self._active_tools:
            lines.append("\n### 🔧 Active MCP Tools")
            for tool in self._active_tools:
                desc = getattr(tool, 'description', 'No description')
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                lines.append(f"- `{tool.name}`: {desc}")

        return "\n".join(lines)

    # 保持向后兼容
    def get_active_mcp_context(self) -> str:
        return self.get_mcp_context()

    def list_servers(self):
        """在控制台列出所有 MCP 服务器"""
        self._discover_servers()
        
        if not self.servers:
            console.print("[dim]📡 没有配置 MCP 服务器[/dim]")
            console.print(f"[dim]   在 {self.config_dir}/ 下创建 JSON 配置文件来添加 MCP 服务器[/dim]")
            return
        
        table = Table(title="📡 MCP Servers")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Transport", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Tools", style="magenta")
        table.add_column("Description", style="white")
        
        for name, server in self.servers.items():
            if server.active:
                status = "🟢 Active"
            elif server.enabled:
                status = "🟡 Enabled"
            else:
                status = "⚪ Available"
            
            transport = server.transport
            tools = str(server.tools_count) if server.active else "-"
            
            desc = server.description[:50] + "..." if len(server.description) > 50 else server.description
            
            table.add_row(name, transport, status, tools, desc)
        
        console.print(table)

    def refresh(self):
        """刷新 MCP 服务器列表"""
        self._discover_servers()


# 全局单例
_mcp_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    """获取全局 MCPManager 实例"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager


# ==================== Agent 可调用的 MCP 工具函数（只读） ====================

from langchain_core.tools import tool


@tool
def list_mcp_servers() -> str:
    """
    列出所有可用的 MCP 服务器及其状态，以及每个已激活服务器提供的具体工具。
    
    使用此工具来了解当前环境中有哪些 MCP 服务器可用，
    每个服务器提供了哪些工具（仅已激活的可见具体工具名）。
    
    注意：MCP 服务器的激活和反激活只能由用户在 TUI 侧边栏手动操作，
         你无法自行激活/反激活，只能查看状态。
    
    Returns:
        MCP 服务器列表、状态及已激活服务器的工具详情
    """
    try:
        mcp = get_mcp_manager()
        mcp.refresh()
        
        available = mcp.get_available_servers()
        active = mcp.get_active_servers()
        active_tools = mcp.get_active_tools()
        
        if not available:
            return """[NO_MCP] 📡 当前没有配置 MCP 服务器。

💡 配置方法:
在 ~/.qoze/mcp/ 目录下创建 JSON 配置文件，例如:

**math_server.json** (stdio 传输):
```json
{
  "name": "math",
  "transport": "stdio",
  "command": "python",
  "args": ["/path/to/math_server.py"],
  "description": "数学运算服务器",
  "enabled": false
}
```

**weather_server.json** (http 传输):
```json
{
  "name": "weather",
  "transport": "http",
  "url": "http://localhost:8000/mcp",
  "headers": {},
  "description": "天气查询服务器",
  "enabled": false
}
```

使用 get_mcp_install_guide 获取详细安装指引。"""
        
        result = f"📡 MCP 服务器列表 ({len(available)} 个可用, {len(active)} 个激活):\n\n"
        
        active_names = set(active.keys())
        
        for name, desc in available.items():
            if name in active_names:
                server = active[name]
                result += f"🟢 **{name}** [ACTIVE]\n"
                result += f"   描述: {desc}\n"
                result += f"   传输: {server.transport}\n"
                result += f"   工具数: {server.tools_count}\n"
                
                server_tools = [t for t in active_tools
                               if hasattr(t, 'metadata') and t.metadata
                               and t.metadata.get('_mcp_server') == name]
                if server_tools:
                    result += "   工具列表:\n"
                    for t in server_tools:
                        tool_desc = getattr(t, 'description', 'No description')
                        if len(tool_desc) > 120:
                            tool_desc = tool_desc[:117] + "..."
                        result += f"     • `{t.name}`: {tool_desc}\n"
                elif server.tools_count > 0:
                    result += "   工具列表:\n"
                    for t in active_tools:
                        tool_desc = getattr(t, 'description', 'No description')
                        if len(tool_desc) > 120:
                            tool_desc = tool_desc[:117] + "..."
                        result += f"     • `{t.name}`: {tool_desc}\n"
                else:
                    result += "   工具列表: (加载中...)\n"
                result += "\n"
        
        for name, desc in available.items():
            if name not in active_names:
                result += f"⚪ **{name}** [INACTIVE]\n"
                result += f"   描述: {desc}\n"
                result += f"   工具: 需激活后查看\n\n"
        
        result += "💡 提示: MCP 服务器的激活/反激活请在 TUI 侧边栏手动操作。"
        return result
        
    except Exception as e:
        error_msg = f"[MCP_ERROR] 获取 MCP 服务器列表时发生错误: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        return error_msg


@tool
def get_mcp_install_guide(server_name: str = None) -> str:
    """
    获取 MCP 服务器的安装和配置指引。
    
    当需要添加新的 MCP 服务器时，调用此工具获取详细的配置步骤。
    此工具只返回指引，不执行实际安装。
    
    Args:
        server_name: 要安装的 MCP 服务器名称（可选）。如不提供则返回通用指引。
        
    Returns:
        详细的安装和配置指引
    """
    try:
        mcp = get_mcp_manager()
        config_dir = mcp.config_dir
        
        guide = f"""📘 MCP 服务器安装与配置指引
{'=' * 60}

## 什么是 MCP？
MCP (Model Context Protocol) 是一种开放协议，让外部服务器可以为 LLM 提供额外的工具。
通过 MCP，你可以：
- 连接数据库、API、文件系统等外部资源
- 使用第三方开发的专用工具
- 扩展 Agent 的能力边界

## 配置目录
所有 MCP 服务器配置存放在: {config_dir}/

## 配置步骤

### 步骤 1: 创建 JSON 配置文件
在 {config_dir}/ 下创建一个 JSON 文件，文件名任意（如 my_server.json）。

### 步骤 2-1: stdio 传输配置（本地进程通信）
适用于本地运行的 MCP 服务器：
```json
{{
  "name": "{server_name or 'my_mcp_server'}",
  "transport": "stdio",
  "command": "python",
  "args": ["/absolute/path/to/server.py"],
  "env": {{}},
  "description": "服务器描述",
  "enabled": false
}}
```

字段说明：
- **name**: 服务器唯一名称（必填）
- **transport**: "stdio" 表示通过标准输入输出通信
- **command**: 启动命令（如 python, node, uvx 等）
- **args**: 命令参数列表（必填，第一个元素通常是脚本路径）
- **env**: 环境变量（可选）
- **description**: 服务器描述（可选）
- **enabled**: 是否默认启用（可选，默认 false）

### 步骤 2-2: HTTP 传输配置（远程服务器通信）
适用于远程运行的 MCP 服务器：
```json
{{
  "name": "{server_name or 'my_mcp_server'}",
  "transport": "http",
  "url": "http://localhost:8000/mcp",
  "headers": {{
    "Authorization": "Bearer YOUR_TOKEN"
  }},
  "description": "服务器描述",
  "enabled": false
}}
```

字段说明：
- **transport**: "http" 或 "streamable-http"
- **url**: MCP 服务器端点 URL（必填）
- **headers**: 自定义 HTTP 请求头（可选，用于认证等）

### 步骤 3: 验证配置
1. 确保 langchain-mcp-adapters 已安装: pip install langchain-mcp-adapters
2. 配置文件放入 {config_dir}/ 后重启 TUI
3. 在 TUI 侧边栏中查看 MCP 服务器列表
4. 在侧边栏手动激活服务器
5. 激活后可调用 list_mcp_servers() 查看工具是否加载成功

### 步骤 4: 创建自定义 MCP 服务器
使用 FastMCP 库快速创建 MCP 服务器:

```python
from fastmcp import FastMCP

mcp = FastMCP("{server_name or 'MyServer'}")

@mcp.tool()
def my_tool(param: str) -> str:
    \"\"\"工具描述\"\"\"
    return f"Result: {{param}}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

安装 FastMCP: pip install fastmcp

## 常见问题
- **工具未加载**: 检查服务器是否正常运行，查看终端输出是否有报错
- **stdio 连接失败**: 确保 command 和 args 正确，脚本路径为绝对路径
- **http 连接失败**: 确保服务器已在指定端口启动，URL 可访问
- **依赖缺失**: 确保 langchain-mcp-adapters 已安装

## 配置示例
在 {config_dir}/ 目录下查看或创建配置文件。
"""
        
        return guide
        
    except Exception as e:
        error_msg = f"[MCP_ERROR] 获取安装指引时发生错误: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        return error_msg
