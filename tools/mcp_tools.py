"""
QozeCode MCP Tools - LLM 可调用的 MCP 管理工具
对标 skill_tools.py 的设计
"""

from langchain_core.tools import tool
from shared_console import console, is_tui_mode


# 全局 MCP 管理器实例（由 qoze_code_agent.py 注入）
_mcp_manager = None


def set_mcp_manager(manager):
    """设置全局 MCP 管理器实例"""
    global _mcp_manager
    _mcp_manager = manager


def get_mcp_manager():
    """获取全局 MCP 管理器实例"""
    global _mcp_manager
    if _mcp_manager is None:
        raise RuntimeError("MCPManager not initialized")
    return _mcp_manager


def _log(msg: str, style: str = "dim"):
    """仅在非 TUI 模式下输出日志到终端"""
    if not is_tui_mode():
        console.print(f"[{style}]{msg}[/{style}]")


@tool
async def list_mcp_servers() -> str:
    """列出所有已配置的 MCP (Model Context Protocol) 服务及其状态。

    使用此工具来了解当前环境中有哪些 MCP 服务可用，哪些已激活。
    每个 MCP 服务可以提供额外的工具（如数据库查询、API 调用等）。

    Returns:
        格式化的服务列表：名称、描述、传输类型、激活状态、工具数
    """
    try:
        mgr = get_mcp_manager()
        servers = mgr.list_servers()

        if not servers:
            return "[NO_MCP_SERVERS] 当前没有配置任何 MCP 服务。\n" \
                   "你可以在 ~/.qoze/mcp_config.json 中配置 MCP 服务。"

        lines = ["MCP 服务列表:"]
        for name, desc in servers.items():
            status = mgr.get_server_status(name)
            if status:
                active_str = "🟢 已激活" if status["active"] else "⚪ 未激活"
                disabled_str = " [已禁用]" if not status["enabled"] else ""
                lines.append(
                    f"  • **{name}** ({active_str}){disabled_str}: {desc}"
                )
                if status["active"] and status["tools"]:
                    tools_str = ", ".join(f"`{t}`" for t in status["tools"])
                    lines.append(f"    工具 ({status['tool_count']}): {tools_str}")

        result = "\n".join(lines)

        # 仅在非 TUI 模式下显示到控制台
        _log(result)

        return result

    except Exception as e:
        error_msg = f"[MCP_ERROR] 获取 MCP 服务列表失败: {str(e)}"
        _log(error_msg, "red")
        return error_msg


@tool
async def activate_mcp_server(server_name: str) -> str:
    """激活指定的 MCP 服务，使其工具对 Agent 可用。

    激活后，该服务提供的所有工具将自动注册到当前会话，你可以像使用内置工具一样调用它们。
    如果服务已经激活，返回当前工具列表。

    Args:
        server_name: MCP 服务名称（如 "postgres", "weather"）

    Returns:
        激活结果，包含该服务提供的工具列表
    """
    try:
        mgr = get_mcp_manager()

        # chrome-devtools 特殊处理：先确保独立 Chrome 实例在运行，再激活 MCP
        if server_name == "chrome-devtools":
            import subprocess, os
            chrome_script = os.path.expanduser("~/.qoze/chrome-mcp.sh")
            # 检测 Chrome 远程调试端口
            check = subprocess.run(
                ["curl", "-s", "--max-time", "2", "http://127.0.0.1:9222/json/version"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if check.returncode != 0:
                _log("MCP: Chrome 未运行，正在自动启动...", "yellow")
                # 尝试通过便捷脚本启动
                if os.path.exists(chrome_script):
                    subprocess.run(["bash", chrome_script, "start"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    # fallback: 直接启动 Chrome
                    subprocess.Popen(
                        ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                         "--remote-debugging-port=9222",
                         f"--user-data-dir={__import__('os').path.expanduser('~')}/.qoze/chrome-mcp-profile",
                         "--no-first-run", "--no-default-browser-check"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                # 等待 Chrome 远程调试端口就绪
                for _ in range(10):
                    await __import__('asyncio').sleep(1)
                    r = subprocess.run(
                        ["curl", "-s", "--max-time", "2", "http://127.0.0.1:9222/json/version"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    if r.returncode == 0:
                        _log("MCP: Chrome 独立实例已就绪", "green")
                        break

        # 统一调用激活（无论 Chrome 是否已在运行）
        tools, msg = await mgr.activate_server(server_name)

        if tools:
            # 实时注入到全局工具表
            from qoze_code_agent import tools_by_name, _ASYNC_TOOL_NAMES
            for tool_obj in tools:
                # 冲突检测：内置工具优先
                if tool_obj.name in tools_by_name:
                    prefixed_name = f"{server_name}__{tool_obj.name}"
                    _log(f"MCP: Tool name conflict '{tool_obj.name}' → '{prefixed_name}'", "yellow")
                    tools_by_name.pop(tool_obj.name, None)
                    _ASYNC_TOOL_NAMES.discard(tool_obj.name)
                tools_by_name[tool_obj.name] = tool_obj
                _ASYNC_TOOL_NAMES.add(tool_obj.name)

            # 运行时重新绑定 llm_with_tools，让 LLM 下次调用时看到新工具
            from qoze_code_agent import llm_with_tools, llm
            if llm and llm_with_tools:
                all_tools = list(tools_by_name.values())
                import qoze_code_agent
                qoze_code_agent.llm_with_tools = llm.bind_tools(all_tools)

        _log(f"MCP: {msg}", "green")
        return msg

    except Exception as e:
        error_msg = f"[MCP_ERROR] 激活 MCP 服务失败: {str(e)}"
        _log(error_msg, "red")
        return error_msg


@tool
async def deactivate_mcp_server(server_name: str) -> str:
    """反激活指定的 MCP 服务，断开连接并卸载其工具。

    反激活后该服务提供的工具将从当前会话中移除。
    如果服务未激活，返回提示信息。

    Args:
        server_name: 要反激活的 MCP 服务名称

    Returns:
        反激活结果
    """
    try:
        mgr = get_mcp_manager()

        removed_tools, msg = await mgr.deactivate_server(server_name)

        if removed_tools:
            # 从全局工具表中移除
            from qoze_code_agent import tools_by_name, _ASYNC_TOOL_NAMES
            for tool_obj in removed_tools:
                tools_by_name.pop(tool_obj.name, None)
                _ASYNC_TOOL_NAMES.discard(tool_obj.name)

            # 运行时重新绑定
            from qoze_code_agent import llm_with_tools, llm
            if llm and llm_with_tools:
                all_tools = list(tools_by_name.values())
                import qoze_code_agent
                qoze_code_agent.llm_with_tools = llm.bind_tools(all_tools)

        _log(f"MCP: {msg}", "yellow")
        return msg

    except Exception as e:
        error_msg = f"[MCP_ERROR] 反激活 MCP 服务失败: {str(e)}"
        _log(error_msg, "red")
        return error_msg
