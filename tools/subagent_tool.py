#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subagent 调度工具 - 实现 LangChain Subagents 模式

核心设计（参考 LangChain 官方文档 Subagents 模式）：
- 主 Agent (Supervisor) 通过工具调用派发任务给 subagent
- Subagent 是无状态的，每次调用在干净的上下文中独立执行
- 主 Agent 可在单轮中同时发起多个 subagent 调用，LangGraph 自动并行执行
- 上下文隔离：subagent 不继承主 agent 的对话历史，避免上下文膨胀
- 统一 System Prompt：subagent 复用主 agent 的静态 system prompt（去掉不可用的 Subagent 调度章节）
- Graph 架构完全模仿主 agent：llm_call → should_continue → tool_node → should_continue_from_tool → llm_call
"""

import asyncio
import operator
import time
import traceback
import uuid
from typing import Literal, Annotated, Optional, Callable, Awaitable

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

from shared_console import console

# ============================================================
# Subagent Stream Callback —— TUI 注册此回调来接收 subagent 实时输出
# ============================================================

# 回调签名: async (event: dict) -> None
# event 格式:
#   {"type": "subagent_start",  "agent_id": str, "label": str}
#   {"type": "subagent_think",  "agent_id": str, "content": str}
#   {"type": "subagent_content","agent_id": str, "content": str}
#   {"type": "subagent_tool",   "agent_id": str, "tool_name": str, "tool_args": str, "status": "start"|"end"}
#   {"type": "subagent_done",   "agent_id": str, "result": str, "stats": dict}
_subagent_stream_callback: Optional[Callable[[dict], Awaitable[None]]] = None


def set_subagent_stream_callback(cb: Optional[Callable[[dict], Awaitable[None]]]):
    """注册 subagent 流式回调。TUI 层调用此函数。传 None 取消注册。"""
    global _subagent_stream_callback
    _subagent_stream_callback = cb


# ============================================================
# Subagent 专用 System Prompt（从 system_prompt.py 加载）
# ============================================================

_subagent_system_prompt_cache = None
_subagent_system_prompt_lock = asyncio.Lock()


async def _get_subagent_system_prompt() -> str:
    """获取 subagent 专用 system prompt（带缓存，并发安全）"""
    global _subagent_system_prompt_cache
    if _subagent_system_prompt_cache is None:
        async with _subagent_system_prompt_lock:
            if _subagent_system_prompt_cache is None:
                from utils.system_prompt import get_subagent_system_prompt
                _subagent_system_prompt_cache = get_subagent_system_prompt()
    return _subagent_system_prompt_cache


def _load_rules() -> str:
    """加载当前工作目录下 .qoze/rules/ 的自定义规则（与主 agent 一致）"""
    import os
    current_dir = os.getcwd()
    rules_dir = os.path.join(current_dir, '.qoze', 'rules')
    if not os.path.isdir(rules_dir):
        return ""

    try:
        rule_files = [f for f in os.listdir(rules_dir) if os.path.isfile(os.path.join(rules_dir, f))]
        if not rule_files:
            return ""

        parts = ["\n## 当前自定义 agent 规则\n"]
        for file_name in sorted(rule_files):
            file_path = os.path.join(rules_dir, file_name)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                parts.append(f"### {file_name}\n{file_content}\n")
            except Exception:
                pass
        return "".join(parts)
    except Exception:
        return ""


def _load_directory_tree() -> str:
    """加载当前目录结构树（与主 agent 一致）"""
    import os
    import asyncio
    try:
        from utils.directory_tree import get_directory_tree
        current_dir = os.getcwd()
        tree = get_directory_tree(current_dir)
        if tree and tree.strip():
            return f"\n## 当前项目目录\n```\n{tree}\n```\n"
    except Exception:
        pass
    return ""


# ============================================================
# Subagent 可用工具 —— 除 browser / skill / subagent 之外的全部工具
# ============================================================

_subagent_tools_cache = None

# 需要用 ainvoke 调用的异步工具名
_SUBAGENT_ASYNC_TOOLS = {
    "tavily_search", "read_url", "execute_command", "read_lark_document",
}


def _get_subagent_tools():
    """获取 subagent 可用的完整工具列表（排除 browser、skill、subagent 工具，带缓存）"""
    global _subagent_tools_cache
    if _subagent_tools_cache is not None:
        return _subagent_tools_cache

    from tools.execute_command_tool import execute_command
    from tools.file_tools import (
        read_file, list_files, list_dir, find_files,
        grep_file, search_in_files,
    )
    from tools.search_tool import tavily_search, read_url
    from tools.math_tools import multiply, add, divide

    _subagent_tools_cache = [
        execute_command,
        read_file, list_files, list_dir, find_files, grep_file, search_in_files,
        tavily_search, read_url,
        multiply, add, divide,
    ]
    return _subagent_tools_cache


# ============================================================
# Subagent 状态 —— 模仿主 agent 的 MessagesState
# ============================================================

class SubagentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int


# 最大 ReAct 迭代次数
MAX_SUBAGENT_ITERATIONS = 10  # 从 15 降到 10，更快兜底


# ============================================================
# 工具参数格式化（用于日志输出）
# ============================================================

def _format_tool_args(tool_name: str, args: dict) -> str:
    """格式化工具参数为简洁可读的日志字符串"""
    if not args:
        return ""
    if tool_name == "tavily_search":
        query = args.get("query", "")
        max_results = args.get("max_results", "")
        parts = [f'"{query}"']
        if max_results:
            parts.append(f"max={max_results}")
        return ", ".join(parts)
    elif tool_name == "read_url":
        url = args.get("url", "")
        if len(url) > 60:
            url = url[:57] + "..."
        return f'"{url}"'
    elif tool_name == "read_file":
        path = args.get("path", "")
        start = args.get("start_line")
        end = args.get("end_line")
        parts = [f'"{path}"']
        if start or end:
            parts.append(f"L{start or 1}-{end or '...'}")
        return ", ".join(parts)
    elif tool_name in ("execute_command",):
        cmd = args.get("command", "")
        if len(cmd) > 80:
            cmd = cmd[:77] + "..."
        return f'"{cmd}"'
    elif tool_name == "read_lark_document":
        url = args.get("url", "")
        if len(url) > 60:
            url = url[:57] + "..."
        return f'"{url}"'
    elif tool_name in ("grep_file", "search_in_files"):
        keyword = args.get("keyword", "") or args.get("pattern", "")
        path = args.get("path", "") or args.get("directory", "")
        parts = []
        if keyword:
            parts.append(f'"{keyword}"')
        if path:
            parts.append(f'"{path}"')
        return ", ".join(parts) if parts else ""
    else:
        first_key = next(iter(args))
        first_val = str(args[first_key])
        if len(first_val) > 50:
            first_val = first_val[:47] + "..."
        return f'{first_key}="{first_val}"'


# ============================================================
# Subagent Graph 构建 —— 完全模仿主 agent 的架构
# ============================================================

def _build_subagent(model_with_tools):
    """
    构建 subagent 的 LangGraph agent，架构完全对标主 agent：

    START → llm_call → should_continue ──→ tool_node → should_continue_from_tool ──→ llm_call
                          │                                                │
                          └──→ END                                         └──→ END

    无 checkpointer（无状态 subagent），每次调用独立执行。
    system_prompt 在运行时动态注入。
    model_with_tools 只绑定了 subagent 专属工具（不含 browser/skill）。
    """

    # --------------------------------------------------
    # Node 1: llm_call —— 模型推理节点
    # --------------------------------------------------
    async def _subagent_llm_call(state: SubagentState):
        """Subagent 的 LLM 调用节点（对标主 agent 的 llm_call）"""
        msgs = state["messages"]
        round_num = state.get("llm_calls", 0) + 1
        try:
            response = await model_with_tools.ainvoke(msgs)
            tc_names = [tc["name"] for tc in response.tool_calls] if response.tool_calls else []
            if tc_names:
                console.print(f"[dim]  🔄 Subagent 第{round_num}轮推理 → 准备调用: {', '.join(tc_names)}[/dim]")
            else:
                console.print(f"[dim]  ✅ Subagent 第{round_num}轮推理 → 任务完成，返回结果[/dim]")
            return {
                "messages": [response],
                "llm_calls": round_num,
            }
        except Exception as e:
            error_msg = f"Subagent LLM error: {type(e).__name__}: {e}"
            console.print(f"[red]{error_msg}[/red]")
            return {
                "messages": [AIMessage(content=error_msg)],
                "llm_calls": round_num,
            }

    # --------------------------------------------------
    # Node 2: tool_node —— 工具执行节点
    # --------------------------------------------------
    async def _subagent_tool_node(state: SubagentState):
        """Subagent 的工具执行节点（对标主 agent 的 tool_node）"""
        subagent_tools = _get_subagent_tools()
        tools_by_name = {t.name: t for t in subagent_tools}
        result = []

        for tool_call in state["messages"][-1].tool_calls:
            tool_name = tool_call["name"]
            args = tool_call["args"]
            args_summary = _format_tool_args(tool_name, args)
            round_num = state.get("llm_calls", 0) + 1
            console.print(f"[cyan] [{round_num}] {tool_name}({args_summary})[/cyan]")
            try:
                t = tools_by_name[tool_name]
                if tool_name in _SUBAGENT_ASYNC_TOOLS:
                    observation = await t.ainvoke(args)
                else:
                    observation = t.invoke(args)
                result.append(ToolMessage(
                    content=observation,
                    tool_call_id=tool_call["id"],
                    name=tool_name
                ))
            except KeyError:
                result.append(ToolMessage(
                    content=(
                        f"Tool '{tool_name}' not available to subagent. "
                        f"Available: {', '.join(sorted(tools_by_name.keys()))}"
                    ),
                    tool_call_id=tool_call["id"],
                    name=tool_name
                ))
            except Exception as e:
                traceback.print_exc()
                result.append(ToolMessage(
                    content=f"Tool '{tool_name}' error: {type(e).__name__}: {e}",
                    tool_call_id=tool_call["id"],
                    name=tool_name
                ))

        return {"messages": result}

    # --------------------------------------------------
    # Edge 1: should_continue —— llm_call 后判断
    # --------------------------------------------------
    def _should_continue(state: SubagentState) -> Literal["tool_node", END]:
        messages = state["messages"]
        last_message = messages[-1]

        if state.get("llm_calls", 0) > MAX_SUBAGENT_ITERATIONS:
            console.print(f"[yellow]⚠️ Subagent 达到最大迭代次数 {MAX_SUBAGENT_ITERATIONS}，强制结束[/yellow]")
            return END

        if last_message.tool_calls:
            return "tool_node"

        return END

    # --------------------------------------------------
    # Edge 2: should_continue_from_tool —— tool_node 后判断
    # --------------------------------------------------
    def _should_continue_from_tool(state: SubagentState) -> Literal["llm_call", END]:
        if state.get("llm_calls", 0) > MAX_SUBAGENT_ITERATIONS:
            console.print(f"[yellow]⚠️ Subagent 达到最大迭代次数 {MAX_SUBAGENT_ITERATIONS}，强制结束[/yellow]")
            return END

        return "llm_call"

    # --------------------------------------------------
    # 组装 Graph
    # --------------------------------------------------
    builder = StateGraph(SubagentState)

    builder.add_node("llm_call", _subagent_llm_call)
    builder.add_node("tool_node", _subagent_tool_node)

    builder.add_edge(START, "llm_call")
    builder.add_conditional_edges(
        "llm_call",
        _should_continue,
        ["tool_node", END]
    )
    builder.add_conditional_edges(
        "tool_node",
        _should_continue_from_tool,
        ["llm_call", END]
    )

    return builder.compile()


# ============================================================
# 全局缓存
# ============================================================

_subagent_instance = None
_subagent_instance_lock = asyncio.Lock()


async def _get_or_build_subagent():
    """
    获取或构建 subagent graph 实例（单例缓存，并发安全）。

    关键优化：为 subagent 创建独立的 llm_with_tools，只绑定 subagent 专属工具，
    而不是复用主 agent 的 llm_with_tools（后者绑定了 31 个工具，subagent 只能用 10 个）。
    消除每次 LLM 调用中 21 个无用工具 schema 的传输开销。
    """
    global _subagent_instance
    if _subagent_instance is None:
        async with _subagent_instance_lock:
            if _subagent_instance is None:
                import qoze_code_agent
                llm = qoze_code_agent.llm
                if llm is None:
                    raise RuntimeError("主 agent 的 LLM 尚未初始化")
                subagent_tools = _get_subagent_tools()
                subagent_llm_with_tools = llm.bind_tools(subagent_tools)
                _subagent_instance = _build_subagent(subagent_llm_with_tools)
    return _subagent_instance


def reset_subagent_cache():
    """清除所有缓存的 subagent。在模型切换或重置会话时调用。"""
    global _subagent_instance, _subagent_tools_cache, _subagent_system_prompt_cache
    _subagent_instance = None
    _subagent_tools_cache = None
    _subagent_system_prompt_cache = None
    console.print("[dim]🧹 Subagent 缓存已清除[/dim]")


# ============================================================
# Subagent 流式执行 —— 使用 astream_events 实时输出
# ============================================================

async def _stream_subagent(
        subagent,
        messages: list,
        agent_id: str,
        label: str,
) -> str:
    """
    使用 astream_events 执行 subagent，每轮 LLM 结束时回调完整 AIMessage content。

    不做 token 级流式，不发送 thinking / tool 细节。
    返回最终的文本结果。
    """
    cb = _subagent_stream_callback
    if cb is None:
        # 无回调时回退到 ainvoke
        config = {"recursion_limit": MAX_SUBAGENT_ITERATIONS * 2 + 5}
        result = await asyncio.wait_for(
            subagent.ainvoke({"messages": messages, "llm_calls": 0}, config=config),
            timeout=300.0
        )
        result_messages = result.get("messages", [])
        final = ""
        for msg in reversed(result_messages):
            if isinstance(msg, AIMessage) and msg.content:
                final = msg.content
                break
        return final or "Subagent 执行完成（无文本输出）"

    # --- 回调模式：只关注 on_chat_model_end ---
    await cb({"type": "subagent_start", "agent_id": agent_id, "label": label})

    config = {"recursion_limit": MAX_SUBAGENT_ITERATIONS * 2 + 5}
    final_content = ""
    total_llm_calls = 0
    total_tool_calls = 0

    try:
        async for event in subagent.astream_events(
                {"messages": messages, "llm_calls": 0},
                config=config,
                version="v2",
        ):
            kind = event["event"]

            # LLM 流式输出 —— 逐 token 发送
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if hasattr(chunk, "content") and chunk.content:
                    text = chunk.content
                    if isinstance(text, str) and text:
                        final_content += text
                        await cb({
                            "type": "subagent_stream",
                            "agent_id": agent_id,
                            "content": text,
                        })

            # LLM 调用结束 —— 本轮完成
            elif kind == "on_chat_model_end":
                total_llm_calls += 1

            # 工具开始
            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event["data"].get("input", {})
                args_summary = _format_tool_args(tool_name, tool_input)
                await cb({
                    "type": "subagent_tool",
                    "agent_id": agent_id,
                    "tool_name": tool_name,
                    "tool_args": args_summary,
                    "status": "start",
                })

            # 工具结束
            elif kind == "on_tool_end":
                total_tool_calls += 1
                tool_name = event.get("name", "unknown")
                await cb({
                    "type": "subagent_tool",
                    "agent_id": agent_id,
                    "tool_name": tool_name,
                    "tool_args": "",
                    "status": "end",
                })

    except asyncio.CancelledError:
        # 被 dispatch_subagent 的 wait_for 取消，直接向上抛
        raise

    except Exception as e:
        traceback.print_exc()
        error_msg = f"❌ Subagent 执行失败: {type(e).__name__}: {e}"
        await cb({
            "type": "subagent_done",
            "agent_id": agent_id,
            "result": error_msg,
            "stats": {"llm_calls": total_llm_calls, "tool_calls": total_tool_calls},
        })
        return error_msg

    # --- 完成 ---
    stats = {"llm_calls": total_llm_calls, "tool_calls": total_tool_calls}
    await cb({
        "type": "subagent_done",
        "agent_id": agent_id,
        "result": final_content,
        "stats": stats,
    })

    stats_str = f"\n\n---\n📊 Subagent 统计: {total_llm_calls} 轮推理, {total_tool_calls} 次工具调用"
    return final_content + stats_str


# ============================================================
# Subagent 调度工具（异步版本）
# ============================================================

@tool
async def dispatch_subagent(
        task: str,
        context: Optional[str] = None,
) -> str:
    """
    派遣一个专门的子代理 (subagent) 来独立完成一个子任务。

    当你有多个独立的子任务需要并行处理，或者某个任务需要专门的关注时，
    使用此工具将任务分派给子代理。你可以在单轮中同时调用多个 dispatch_subagent
    来并行执行多个子任务（LangGraph 自动并行执行所有 tool_calls）。

    Subagent 会自动使用与主 Agent 相同的系统提示和工作原则，通过 task 描述来
    明确子任务的具体要求。

    Args:
        task: 要分配给子代理的具体任务描述，越详细越好
        context: 可选，为子代理提供额外的背景信息（如相关文件路径、项目约定等）

    Returns:
        子代理完成任务的完整报告
    """

    try:
        subagent = await _get_or_build_subagent()

        # 统一使用主 Agent 的 system prompt（去掉不可用的章节）
        effective_system_prompt = await _get_subagent_system_prompt()

        # 生成唯一 ID 和标签
        agent_id = str(uuid.uuid4())[:8]
        label = task[:60] + "..." if len(task) > 60 else task

        user_content = f"## Task\n{task}"
        if context:
            user_content += f"\n\n## Additional Context\n{context}"
        user_content += "\n\nComplete the task and return a clear summary of what you did and the results."

        # 加载 .qoze/rules 规则并注入到 system prompt
        rules = _load_rules()
        if rules:
            effective_system_prompt = effective_system_prompt + "\n" + rules

        # 加载目录树注入到 user message
        directory_tree = _load_directory_tree()
        if directory_tree:
            user_content = directory_tree + "\n" + user_content

        messages = [
            SystemMessage(content=effective_system_prompt),
            HumanMessage(content=user_content),
        ]

        # 使用流式执行（如果 TUI 注册了回调），否则回退到 ainvoke
        # 注意：asyncio.wait_for 包裹整个流式执行，600s 超时
        return await asyncio.wait_for(
            _stream_subagent(subagent, messages, agent_id, label),
            timeout=600.0
        )

    except asyncio.TimeoutError:
        return "⚠️ Subagent 执行超时，任务可能过于复杂。请尝试拆分为更小的子任务。"
    except Exception as e:
        traceback.print_exc()
        return f"❌ Subagent 执行失败: {type(e).__name__}: {e}"
