#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP 客户端封装 - 管理 MultiServerMCPClient 的连接和工具加载
"""
import os
import asyncio
from typing import Dict, List, Optional
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool
from shared_console import console, is_tui_mode


# 注入到 MCP 子进程的环境变量，抑制 npx/npm/Node.js 的终端输出
_SILENCE_ENV = {
    "NPM_CONFIG_LOGLEVEL": "silent",
    "npm_config_loglevel": "silent",
    "NO_UPDATE_NOTIFIER": "1",
    "NODE_NO_WARNINGS": "1",
    "npm_config_update_notifier": "false",
}


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

        # 构建环境变量：合并用户配置 + 静默抑制变量（用户配置优先级更高）
        env = dict(_SILENCE_ENV)
        if config.env:
            env.update(config.env)

        if config.transport == "stdio":
            server_config["transport"] = "stdio"
            server_config["command"] = config.command
            # npx 自动追加 --quiet 和 --no-install（首次安装后无需重复检查）
            if config.args:
                args = list(config.args)
                if config.command == "npx" and "--quiet" not in args:
                    args.insert(0, "--quiet")
                server_config["args"] = args
            else:
                server_config["args"] = config.args
            server_config["env"] = env
        elif config.transport == "http":
            server_config["transport"] = "http"
            server_config["url"] = config.url
            if config.headers:
                server_config["headers"] = config.headers

        return server_config

    async def connect_all(self, servers: dict) -> List[BaseTool]:
        """一次性连接所有指定的 MCP 服务并加载工具

        在 TUI 模式下，会临时重定向 stderr 到 /dev/null，防止 MCP 子进程的输出
        （如 npx 安装日志、Node.js 警告等）破坏 Textual 界面渲染。

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

        # TUI 模式下临时重定向 stderr，防止子进程输出破坏界面
        _saved_stderr = None
        _null_fd = None
        if is_tui_mode():
            _saved_stderr = os.dup(2)
            _null_fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(_null_fd, 2)

        try:
            self._client = MultiServerMCPClient(client_config)
            tools = await asyncio.wait_for(
                self._client.get_tools(),
                timeout=self._connection_timeout
            )
            if not is_tui_mode():
                console.print(f"[green]MCP: {len(tools)} tools loaded from {len(client_config)} server(s)[/green]")
            return list(tools) if tools else []
        except asyncio.TimeoutError:
            if not is_tui_mode():
                console.print(f"[red]MCP: Connection timeout ({self._connection_timeout}s)[/red]")
            return []
        except Exception as e:
            if not is_tui_mode():
                console.print(f"[yellow]MCP: Failed to load tools: {e}[/yellow]")
            return []
        finally:
            # 恢复 stderr
            if _saved_stderr is not None:
                os.dup2(_saved_stderr, 2)
                os.close(_saved_stderr)
            if _null_fd is not None:
                os.close(_null_fd)

    async def reconnect_all(self, servers: dict) -> List[BaseTool]:
        """重新连接所有服务（配置热加载后调用）"""
        await self.disconnect_all()
        return await self.connect_all(servers)

    async def disconnect_all(self):
        """断开所有 MCP 连接"""
        if self._client:
            try:
                pass
            except Exception:
                pass
        self._client = None
        self._server_configs = {}

    @property
    def is_connected(self) -> bool:
        return self._client is not None and len(self._server_configs) > 0
