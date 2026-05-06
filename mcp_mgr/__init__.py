#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode MCP (Model Context Protocol) 模块
统一管理 MCP 服务器的发现、激活、工具加载，以及 Agent 可调用的只读工具。
"""

from mcp_mgr.mcp_manager import (
    MCPManager,
    MCPServerConfig,
    get_mcp_manager,
    list_mcp_servers,
    get_mcp_install_guide,
)

__all__ = [
    "MCPManager",
    "MCPServerConfig",
    "get_mcp_manager",
    "list_mcp_servers",
    "get_mcp_install_guide",
]
