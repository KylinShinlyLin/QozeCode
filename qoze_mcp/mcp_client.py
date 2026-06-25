#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP 客户端封装 - 管理 MultiServerMCPClient 的连接和工具加载
"""

import asyncio
from typing import Dict, List, Optional
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool
from shared_console import console


class MCPClientWrapper:
    """MCP 客户端封装，管理 MultiServerMCPClient 的连接和工具加载"""

    def __init__(self, settings: Optional[dict] = None):
        self._client: Optional[MultiServerMCPClient] = None
        self._server_configs: Dict[str, dict] = {}
        self._settings = settings or {}
        self._connection_timeout = self._settings.get("connection_timeout", 30)

    def _build_server_config(self, config) -> dict:
        """将 MCPServerConfig 转换为 MultiServerMCPClient 需要的字典格式"""
        server_config = {}
        
        if config.transport == "stdio":
            server_config["transport"] = "stdio"
            server_config["command"] = config.command
            if config.args:
                server_config["args"] = config.args
            if config.env:
                server_config["env"] = config.env
        elif config.transport == "http":
            server_config["transport"] = "http"
            server_config["url"] = config.url
            if config.headers:
                server_config["headers"] = config.headers

        return server_config

    async def connect_all(self, servers: Dict[str, "MCPServerConfig"]) -> List[BaseTool]:
        """一次性连接所有指定的 MCP 服务并加载工具
        
        Args:
            servers: {server_name: MCPServerConfig} 字典
            
        Returns:
            所有服务提供的工具列表
        """
        if not servers:
            return []

        self._server_configs = {}
        client_config = {}

        for name, config in servers.items():
            server_cfg = self._build_server_config(config)
            if server_cfg:
                client_config[name] = server_cfg
                self._server_configs[name] = server_cfg

        if not client_config:
            return []

        try:
            self._client = MultiServerMCPClient(client_config)
            tools = await asyncio.wait_for(
                self._client.get_tools(),
                timeout=self._connection_timeout
            )
            console.print(f"[green]MCP: {len(tools)} tools loaded from {len(client_config)} server(s)[/green]")
            return list(tools) if tools else []
        except asyncio.TimeoutError:
            console.print(f"[red]MCP: Connection timeout ({self._connection_timeout}s)[/red]")
            return []
        except Exception as e:
            console.print(f"[yellow]MCP: Failed to load tools: {e}[/yellow]")
            return []

    async def reconnect_all(self, servers: Dict[str, "MCPServerConfig"]) -> List[BaseTool]:
        """重新连接所有服务（配置热加载后调用）"""
        await self.disconnect_all()
        return await self.connect_all(servers)

    async def disconnect_all(self):
        """断开所有 MCP 连接"""
        if self._client:
            try:
                # MultiServerMCPClient 支持 context manager 自动清理
                # 强制关闭底层传输
                pass
            except Exception:
                pass
        self._client = None
        self._server_configs = {}

    @property
    def is_connected(self) -> bool:
        return self._client is not None and len(self._server_configs) > 0
