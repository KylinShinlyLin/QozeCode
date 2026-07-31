"""
QozeCode MCP Tools - LLM 可调用的 MCP 管理工具
对标 skill_tools.py 的设计
"""

import os
import platform
import shutil
import asyncio

from langchain_core.tools import tool
from shared_console import console, is_tui_mode
from config_manager import _get_qoze_base_dir


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


def _get_chrome_path() -> str:
    """跨平台检测 Chrome/Chromium 可执行文件路径。

    按平台优先级依次尝试常见安装路径，始终返回一个可用路径。

    Returns:
        Chrome 可执行文件的绝对路径或可执行的命令名
    """
    system = platform.system()
    if system == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif system == "Windows":
        for p in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            __import__('os').path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]:
            if __import__('os').path.exists(p):
                return p
        return "chrome"  # fallback to PATH
    else:  # Linux 等
        for p in ["google-chrome", "chromium-browser", "chromium"]:
            if shutil.which(p):
                return p
        return "google-chrome"


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
                   f"你可以在 {_get_qoze_base_dir()}/mcp_config.json 中配置 MCP 服务。"

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

            # 跨平台脚本路径检测
            if platform.system() == "Windows":
                chrome_script = os.path.join(_get_qoze_base_dir(), "chrome-mcp.ps1")
                use_shell_script = False
            else:
                chrome_script = os.path.join(_get_qoze_base_dir(), "chrome-mcp.sh")
                use_shell_script = True

            # 检测 Chrome 远程调试端口
            check = subprocess.run(
                ["curl", "-s", "--max-time", "2", "http://127.0.0.1:9222/json/version"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if check.returncode != 0:
                _log("MCP: Chrome 未运行，正在自动启动...", "yellow")
                # 尝试通过便捷脚本启动
                if os.path.exists(chrome_script):
                    if use_shell_script:
                        subprocess.run(["bash", chrome_script, "start"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        subprocess.run(["powershell", "-ExecutionPolicy", "Bypass",
                                        "-File", chrome_script, "start"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    # fallback: 跨平台直接启动 Chrome
                    chrome_path = _get_chrome_path()
                    subprocess.Popen(
                        [chrome_path,
                         "--remote-debugging-port=9222",
                         f"--user-data-dir={os.path.expanduser('~')}/.qoze/chrome-mcp-profile",
                         "--no-first-run", "--no-default-browser-check"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                # 等待 Chrome 远程调试端口就绪
                for _ in range(10):
                    await asyncio.sleep(1)
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


@tool
def get_mcp_install_guide(server_name: str = "", server_source: str = "") -> str:
    """
    当需要安装/配置新的 MCP (Model Context Protocol) 服务时调用，获取详细的安装指引。
    此工具只返回安装指引，不执行实际安装。Agent 应该根据返回的指引自行执行安装操作。

    Args:
        server_name: 要安装/配置的 MCP 服务名称（如 "github"、"postgres"、"chrome-devtools"）。留空则返回通用指引
        server_source: 服务来源（可选），可以是：
            - npm 包名（如 "@modelcontextprotocol/server-github"）
            - 官方文档 URL
            - 服务用途描述

    Returns:
        详细的安装指引，包含：
        - 配置文件位置（默认用户级 ~/.qoze/mcp_config.json）
        - 配置格式与字段说明（stdio/http）
        - 前置依赖检查与安装流程
        - 激活与验证步骤（TUI /mcp 命令 或 activate_mcp_server 工具）
        - 常见问题与注意事项
    """
    try:
        # 项目根目录（tools/ 的上一级），用于定位 mcp_config.template.json
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(_get_qoze_base_dir(), "mcp_config.json")
        template_path = os.path.join(project_root, "mcp_config.template.json")

        # 已存在检查（manager 未初始化时跳过）
        mgr, existing = None, {}
        try:
            mgr = get_mcp_manager()
            existing = mgr.list_servers()
        except Exception:
            pass

        if server_name and server_name in existing and mgr is not None:
            status = mgr.get_server_status(server_name)
            active = "已激活" if status and status["active"] else "未激活"
            extra = ""
            if status and status["enabled"] is False:
                extra = " [已禁用]"
            tools_info = ""
            if status and status["tools"]:
                tools_info = "\n工具 ({}): {}".format(status["tool_count"], ", ".join(status["tools"]))
            return (
                f"[MCP_EXISTS] MCP 服务 '{server_name}' 已配置！\n\n"
                f"配置文件: {config_path}\n"
                f"描述: {existing.get(server_name, '')}\n"
                f"状态: {active}{extra}{tools_info}\n\n"
                "如需修改配置，请编辑上述配置文件后重新激活：\n"
                f"  - TUI 下执行 /mcp activate {server_name}（或 /mcp deactivate {server_name}）\n"
                f"  - 或调用 activate_mcp_server('{server_name}')"
            )

        guide_lines = [
            "[MCP_INSTALL_GUIDE] MCP 服务安装指引" + (f"（{server_name}）" if server_name else ""),
            "",
            "=" * 60,
            "配置文件位置（默认用户级）",
            "=" * 60,
            "",
            "QozeCode 的 MCP 服务统一在「用户级配置」中管理（本机所有项目共享）：",
            f"  配置文件: {config_path}",
            f"  参考模板: {template_path}",
            "  模板内含 chrome-devtools / postgres / github 三个示例，可对照修改",
            "",
            "配置目录不存在时先创建:",
            f"  mkdir -p {_get_qoze_base_dir()}",
            "",
            "=" * 60,
            "配置格式（JSON）",
            "=" * 60,
            "",
            "mcp_config.json 顶层包含三部分：",
            '  - servers:        {"服务名": {服务配置}}',
            "  - active_servers: 已激活的服务名列表（用于下次启动自动恢复）",
            "  - settings:       连接超时/重试等全局设置（可选）",
            "",
            "单个服务支持的字段：",
            "  - description: 服务说明（list_mcp_servers 展示用）",
            '  - transport:   "stdio"（本地子进程，默认）或 "http"（远程服务）',
            "  - enabled:     true/false，是否允许激活",
            "",
            "【stdio 传输】用 command 启动本地 MCP server（最常见）：",
            "  - command: 可执行命令（npx / uvx / python3 等）",
            '  - args:     参数列表（如 ["-y", "<npm包>"]）',
            "  - env:      环境变量（密钥类放这里，不要写进命令行）",
            "",
            "【http 传输】连接远程 MCP 服务：",
            "  - url:      服务地址",
            "  - headers:  认证等请求头（如 Authorization）",
            "",
            "完整示例：",
            "```json",
            "{",
            '  "servers": {',
            '    "github": {',
            '      "description": "GitHub API：管理 Issue、PR、仓库",',
            '      "transport": "stdio",',
            '      "command": "npx",',
            '      "args": ["-y", "@modelcontextprotocol/server-github"],',
            '      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx" },',
            '      "enabled": true',
            '    },',
            '    "my-remote": {',
            '      "description": "远程 MCP 服务",',
            '      "transport": "http",',
            '      "url": "https://example.com/mcp",',
            '      "headers": { "Authorization": "Bearer xxx" },',
            '      "enabled": true',
            '    }',
            '  },',
            '  "active_servers": [],',
            '  "settings": {',
            '    "connection_timeout": 60,',
            '    "tool_execution_timeout": 120',
            '  }',
            "}",
            "```",
            "",
        ]

        # 安装流程
        guide_lines.extend([
            "=" * 60,
            "安装流程",
            "=" * 60,
            "",
            "1) 确定服务名称与来源：" + (server_source if server_source else "（未提供来源，需先确认 npm 包名或官方文档）"),
            "",
        ])

        if server_source and server_source.startswith(("http://", "https://")):
            guide_lines.extend([
                "   来源类型: 文档 URL",
                "   建议先阅读官方文档，确认 transport / command / args / 认证方式后继续：",
                f"     {server_source}",
                "",
            ])
        elif server_source and (server_source.startswith("@") or "/" in server_source):
            guide_lines.extend([
                "   来源类型: npm 包名",
                f"   验证包是否存在及用法: npm view {server_source}   或   npx {server_source} --help",
                "",
            ])
        elif server_source:
            guide_lines.extend([
                "   来源类型: 描述/说明",
                "   根据描述判断服务类型与启动方式（stdio 本地进程 或 http 远程服务）",
                "",
            ])

        guide_lines.extend([
            "2) 检查前置依赖（stdio 服务需要本地运行时）：",
            "   - npx 启动: 需要 node/npm（which npx && node --version）",
            "   - uvx 启动: 需要 uv（which uvx）",
            "   - python 启动: 需要对应 python 环境及已安装的 mcp 包",
            "",
            "3) 写入配置：把服务定义加入 servers（enabled: true），保存为 UTF-8 JSON：",
            f"   {config_path}",
            "   示例（用 heredoc 或 python json 写入均可，注意 JSON 语法正确）",
            "",
            "4) 激活并加载工具：",
            f"   - TUI 下执行: /mcp activate {server_name if server_name else '<服务名>'}",
            f"   - 或调用工具: activate_mcp_server('{server_name if server_name else '<服务名>'}')",
            "   - 激活成功会实时把该服务提供的工具注册给 Agent 使用",
            "",
            "5) 验证：",
            "   - list_mcp_servers() 查看服务状态与工具数",
            "   - 实际调用新工具做一次端到端验证",
            "",
        ])

        # 激活与自动恢复
        guide_lines.extend([
            "=" * 60,
            "激活机制与自动恢复",
            "=" * 60,
            "",
            "1) 激活成功后，服务名会自动写入 active_servers，下次启动自动恢复连接。",
            "2) 若 active_servers 为空，启动时会自动激活所有 enabled=true 的服务。",
            "   所以只配置不激活的服务，enabled 可设为 false。",
            "3) 反激活: /mcp deactivate <服务名>  或  deactivate_mcp_server('<服务名>')",
            "4) 修改配置后需重新激活（或重启 QozeCode）才生效：",
            "   - 配置在启动时加载一次；MCPManager 提供 reload_config 支持热加载",
            "",
        ])

        # 注意事项与速查
        guide_lines.extend([
            "=" * 60,
            "注意事项",
            "=" * 60,
            "",
            "1) npx 首次运行会自动下载 npm 包（通常 30-60 秒），属正常现象。",
            "2) 密钥（token/密码）必须放在 env 字段，禁止明文输出到终端/日志/回复。",
            "3) chrome-devtools 特殊：需要 Chrome 9222 远程调试端口；",
            "   activate_mcp_server 会尝试自动拉起独立 Chrome 实例（~/.qoze/chrome-mcp-profile）。",
            "4) 部分官方 @modelcontextprotocol/server-* 包已归档/不再维护，",
            "   不确定时用 `npm view <包名>` 查询更新时间，或选用社区维护的替代包。",
            "5) stdio 服务子进程输出在 TUI 下会被静默抑制，排查问题时可临时在",
            "   非 TUI 模式（命令行启动 qoze）查看日志。",
            "",
            "=" * 60,
            "常见 MCP 服务器速查（供参考，以 npm view 查询为准）",
            "=" * 60,
            "",
            "| 服务 | npm 包 | 额外要求 |",
            "|------|--------|----------|",
            "| github | @modelcontextprotocol/server-github | GITHUB_PERSONAL_ACCESS_TOKEN |",
            "| postgres | @modelcontextprotocol/server-postgres | 连接串参数 |",
            "| filesystem | @modelcontextprotocol/server-filesystem | 允许访问的目录 |",
            "| fetch | @modelcontextprotocol/server-fetch | 无（注意 SSRF 风险） |",
            "| memory | @modelcontextprotocol/server-memory | 知识图谱持久化文件 |",
            "| sequential-thinking | @modelcontextprotocol/server-sequential-thinking | 无 |",
            "| time | @modelcontextprotocol/server-time | 无 |",
            "| chrome-devtools | chrome-devtools-mcp | Chrome 9222 端口 |",
            "",
            "=" * 60,
            "安装后验证步骤（汇总）",
            "=" * 60,
            "",
            "1. cat 配置确认 JSON 合法:",
            f"   cat {config_path}",
            "2. 刷新列表: list_mcp_servers() 或 /mcp list，确认服务已出现",
            "3. 激活: /mcp activate <服务名> 或 activate_mcp_server('<服务名>')",
            "4. 确认工具注册: list_mcp_servers() 显示工具数 > 0",
            "5. 端到端: 实际调用一个新工具验证连通性",
            "",
        ])

        return "\n".join(guide_lines)

    except Exception as e:
        error_msg = f"[MCP_ERROR] 获取 MCP 安装指引时发生错误: {str(e)}"
        _log(error_msg, "red")
        return error_msg
