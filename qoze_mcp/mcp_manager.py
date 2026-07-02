#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP 服务管理器 - 对标 SkillManager 的管理模式
管理 MCP 服务的配置、状态、激活/反激活生命周期
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool
from shared_console import console

from .mcp_client import MCPClientWrapper


@dataclass
class MCPServerConfig:
    """MCP 服务配置数据类"""
    name: str
    description: str = ""
    transport: str = "stdio"          # "stdio" | "http"
    # stdio 字段
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    # http 字段
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "MCPServerConfig":
        return cls(
            name=name,
            description=data.get("description", ""),
            transport=data.get("transport", "stdio"),
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url"),
            headers=data.get("headers", {}),
            enabled=data.get("enabled", True),
        )


class MCPManager:
    """MCP 服务管理器

    对标 SkillManager 的模式：
    - 配置 → 发现 → 激活/反激活 → 工具注入
    - MCP 是纯工具层，不需要 prompt 注入（工具通过 function calling 自动感知）
    """

    def __init__(self, config_manager=None):
        self._servers: Dict[str, MCPServerConfig] = {}
        self._active_servers: List[str] = []
        self._loaded_tools: Dict[str, List[BaseTool]] = {}  # server_name -> [tools]
        self._client_wrapper = MCPClientWrapper()
        self._config_file = Path.home() / ".qoze" / "mcp_config.json"
        self._settings: dict = {}
        self._auto_activated = False  # 是否已经自动激活过
        self._load_config()

    # ─── 配置管理 ─────────────────────────────────────────

    def _load_config(self) -> None:
        """加载 ~/.qoze/mcp_config.json"""
        if not self._config_file.exists():
            return

        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            # 解析 servers
            servers_raw = config.get("servers", {})
            for name, data in servers_raw.items():
                self._servers[name] = MCPServerConfig.from_dict(name, data)

            # 读取激活状态
            self._active_servers = config.get("active_servers", [])

            # 读取全局设置
            self._settings = config.get("settings", {})

            # 更新 client wrapper 设置
            self._client_wrapper = MCPClientWrapper(self._settings)

            console.print(
                f"[dim]MCP: {len(self._servers)} server(s) configured, "
                f"{len(self._active_servers)} active[/dim]"
            )
        except Exception as e:
            console.print(f"[yellow]MCP: Failed to load config: {e}[/yellow]")

    def _save_config(self) -> None:
        """保存配置到 ~/.qoze/mcp_config.json"""
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            config = {
                "servers": {},
                "active_servers": self._active_servers,
                "settings": self._settings,
            }
            for name, server in self._servers.items():
                config["servers"][name] = {
                    "description": server.description,
                    "transport": server.transport,
                    "enabled": server.enabled,
                }
                if server.transport == "stdio":
                    config["servers"][name]["command"] = server.command
                    if server.args:
                        config["servers"][name]["args"] = server.args
                    if server.env:
                        config["servers"][name]["env"] = server.env
                elif server.transport == "http":
                    config["servers"][name]["url"] = server.url
                    if server.headers:
                        config["servers"][name]["headers"] = server.headers

            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            console.print(f"[red]MCP: Failed to save config: {e}[/red]")

    # ─── 自动激活 ─────────────────────────────────────────

    async def auto_activate_all(self) -> List[BaseTool]:
        """自动激活所有 enabled=True 且之前激活过的 MCP 服务。

        在 Agent 首次启动时调用，恢复之前的 MCP 连接状态。
        如果还没有任何激活过的服务，则自动激活所有 enabled=True 的服务。

        Returns:
            List[BaseTool]: 所有激活的工具列表
        """
        if self._auto_activated:
            return []
        self._auto_activated = True

        all_tools = []

        # 确定要激活的服务列表
        if self._active_servers:
            # 之前有激活过的，恢复它们
            targets = [name for name in self._active_servers
                       if name in self._servers and self._servers[name].enabled]
        else:
            # 首次启动，激活所有 enabled 的服务
            targets = [name for name, s in self._servers.items()
                       if s.enabled]

        if not targets:
            console.print("[dim]MCP: No servers to auto-activate[/dim]")
            return []

        console.print(f"[dim]MCP: Auto-activating {len(targets)} server(s): {', '.join(targets)}...[/dim]")

        for name in targets:
            try:
                tools, msg = await self.activate_server(name)
                if tools:
                    all_tools.extend(tools)
                    console.print(f"[green]  ✓ {name}: {len(tools)} tool(s)[/green]")
                elif "ALREADY_ACTIVE" in msg:
                    console.print(f"[dim]  {name}: already active[/dim]")
                else:
                    console.print(f"[yellow]  ⚠ {name}: {msg}[/yellow]")
            except Exception as e:
                console.print(f"[red]  ✗ {name}: {e}[/red]")

        return all_tools

    # ─── 服务查询（供 LLM 工具使用）─────────────────────────

    def list_servers(self) -> Dict[str, str]:
        """返回 {name: description}，供 list_mcp_servers 工具使用"""
        return {name: s.description for name, s in self._servers.items()}

    def get_active_servers_info(self) -> str:
        """返回激活状态摘要（供 list_mcp_servers 工具内部使用，不注入 prompt）"""
        if not self._active_servers:
            return "当前没有激活的 MCP 服务"
        lines = []
        for name in self._active_servers:
            tools = self._loaded_tools.get(name, [])
            server = self._servers.get(name)
            desc = server.description if server else ""
            lines.append(f"- **{name}** ({len(tools)} 个工具): {desc}")
            for t in tools:
                d = (t.description or "")[:100]
                lines.append(f"  - `{t.name}`: {d}")
        return "\n".join(lines)

    def get_server_status(self, name: str) -> Optional[dict]:
        """获取单个服务的详细状态"""
        if name not in self._servers:
            return None
        server = self._servers[name]
        tools = self._loaded_tools.get(name, [])
        return {
            "name": name,
            "description": server.description,
            "transport": server.transport,
            "enabled": server.enabled,
            "active": name in self._active_servers,
            "tool_count": len(tools),
            "tools": [t.name for t in tools],
        }

    # ─── 服务管理（对标 SkillManager）───────────────────────

    async def activate_server(self, name: str) -> tuple:
        """激活 MCP 服务：启动连接 + 加载工具
        
        Returns:
            (List[BaseTool], str): 工具列表和状态消息
        """
        if name not in self._servers:
            return [], f"[MCP_NOT_FOUND] 服务 '{name}' 不存在"

        server = self._servers[name]
        if not server.enabled:
            return [], f"[MCP_DISABLED] 服务 '{name}' 已被禁用"

        if name in self._active_servers:
            # 已激活，直接返回现有工具
            existing_tools = self._loaded_tools.get(name, [])
            tool_names = [t.name for t in existing_tools]
            return existing_tools, (
                f"[MCP_ALREADY_ACTIVE] 服务 '{name}' 已激活，"
                f"提供 {len(existing_tools)} 个工具: {', '.join(tool_names)}"
            )

        # 连接并加载工具
        try:
            tools = await self._client_wrapper.connect_all({name: server})
            self._loaded_tools[name] = tools
            self._active_servers.append(name)
            self._save_config()

            tool_names = [t.name for t in tools]
            console.print(
                f"[green]MCP: Activated '{name}' - {len(tools)} tool(s): "
                f"{', '.join(tool_names)}[/green]"
            )

            return tools, (
                f"[MCP_ACTIVATED] 服务 '{name}' 已激活！\n"
                f"新增 {len(tools)} 个工具: {', '.join(tool_names)}\n"
                f"描述: {server.description}"
            )
        except Exception as e:
            return [], f"[MCP_ERROR] 激活 '{name}' 失败: {e}"

    async def deactivate_server(self, name: str) -> tuple:
        """反激活 MCP 服务：断开连接 + 卸载工具
        
        Returns:
            (List[BaseTool], str): 被卸载的工具列表和状态消息
        """
        if name not in self._active_servers:
            return [], f"[MCP_NOT_ACTIVE] 服务 '{name}' 当前未激活"

        removed_tools = self._loaded_tools.pop(name, [])
        self._active_servers.remove(name)
        self._save_config()

        await self._client_wrapper.disconnect_all()

        # 如果有其他激活服务，重新连接
        if self._active_servers:
            active_configs = {
                n: self._servers[n]
                for n in self._active_servers
                if n in self._servers
            }
            if active_configs:
                self._loaded_tools = {}
                await self._client_wrapper.connect_all(active_configs)

        console.print(f"[yellow]MCP: Deactivated '{name}'[/yellow]")
        return removed_tools, f"[MCP_DEACTIVATED] 服务 '{name}' 已反激活，卸载 {len(removed_tools)} 个工具"

    async def get_active_tools(self) -> List[BaseTool]:
        """获取所有已激活服务的工具列表（启动时调用）"""
        if not self._active_servers:
            return []

        # 如果还没加载过工具，批量连接所有激活服务
        if not self._loaded_tools:
            active_configs = {
                name: self._servers[name]
                for name in self._active_servers
                if name in self._servers and self._servers[name].enabled
            }
            if active_configs:
                all_tools = await self._client_wrapper.connect_all(active_configs)
                # 按服务名分配工具（简单策略：所有工具归第一个服务）
                # TODO: langchain-mcp-adapters 可能提供按服务分组的 API
                if active_configs:
                    first_name = list(active_configs.keys())[0]
                    self._loaded_tools[first_name] = all_tools
                return all_tools

        all_tools = []
        for tools in self._loaded_tools.values():
            all_tools.extend(tools)
        return all_tools

    async def reload_config(self) -> tuple:
        """热加载配置：重新读取 mcp_config.json 并重连
        
        Returns:
            (List[BaseTool], str): 新工具列表和状态消息
        """
        # 记录旧状态
        old_active = set(self._active_servers)

        # 重新加载
        self._loaded_tools.clear()
        await self._client_wrapper.disconnect_all()
        self._servers.clear()
        self._active_servers = []
        self._load_config()

        # 重新激活
        new_active = set(self._active_servers)
        activated = new_active - old_active
        deactivated = old_active - new_active

        tools = await self.get_active_tools()

        msg = "[MCP_RELOADED] 配置已重新加载"
        if activated:
            msg += f"，新增激活: {', '.join(activated)}"
        if deactivated:
            msg += f"，已反激活: {', '.join(deactivated)}"
        msg += f"，共 {len(tools)} 个工具可用"

        return tools, msg

    @property
    def has_servers(self) -> bool:
        return len(self._servers) > 0

    @property
    def has_active_servers(self) -> bool:
        return len(self._active_servers) > 0
