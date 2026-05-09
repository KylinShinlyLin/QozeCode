#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subagent 调度工具 - 实现 LangChain Subagents 模式

核心设计（参考 LangChain 官方文档 Subagents 模式）：
- 主 Agent (Supervisor) 通过工具调用派发任务给 subagent
- Subagent 是无状态的，每次调用在干净的上下文中独立执行
- 主 Agent 可在单轮中同时发起多个 subagent 调用，LangGraph 自动并行执行
- 上下文隔离：subagent 不继承主 agent 的对话历史，避免上下文膨胀
- 动态 System Prompt：主 agent 可根据具体场景为每个 subagent 定制 system prompt
- subagent_type 可选为空：不指定类型时，必须提供 system_prompt 来完全自定义 subagent
- Graph 架构完全模仿主 agent：llm_call → should_continue → tool_node → should_continue_from_tool → llm_call
"""

import asyncio
import operator
import traceback
from typing import Literal, Annotated, Optional

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

from shared_console import console

# ============================================================
# Subagent 类型默认 System Prompt（作为 fallback，main agent 可覆盖）
# ============================================================

SUBAGENT_TYPE_PROMPTS: dict[str, str] = {
    "code-explorer": """You are a **code exploration specialist** subagent. Your mission:
- Search, read, and analyze code files to understand project structure
- Find specific implementations, patterns, dependencies, or logic
- Trace call chains and understand how components connect
- **Do NOT modify any files** — read and search only
- Report findings as a clear, structured summary with file paths and line numbers

Available tools: read_file, execute_command (for grep/find/search), list_files, list_dir, 
search_in_files, grep_file, find_files, replace_in_file.

Return a concise but complete report. If you can't find something, say so explicitly.""",

    "code-writer": """You are a **code implementation specialist** subagent. Your mission:
- Write new code or modify existing files based on given requirements
- Follow existing project conventions, patterns, and code style
- Make minimal, focused, correct changes — avoid unnecessary refactoring
- Use `execute_command` with `sed`, `cat << 'EOF'`, or Python for file modifications
- Use `replace_in_file` for simple text replacements
- **Follow the same safety rules**: don't run builds, tests, or install packages
- After making changes, verify by reading back the modified file

Available tools: read_file, execute_command, list_files, list_dir, search_in_files, 
grep_file, find_files, replace_in_file.

Report exactly what files were changed, what was changed, and why.""",

    "researcher": """You are a **web research specialist** subagent. Your mission:
- Search the web using `tavily_search` for up-to-date information
- Read and extract key information from web pages using `read_url`
- Read Lark/Feishu documents using `read_lark_document` if URLs are provided
- Synthesize findings from multiple sources into a clear report
- Always cite sources (URLs) for any claims
- If search results are insufficient, try different search queries

Available tools: tavily_search, read_url, read_lark_document.

Return a well-organized research report with citations.""",

    "general": """You are a **general task execution** subagent. Your mission:
- Execute the assigned task efficiently using all available tools
- Break down complex tasks into steps and execute them methodically
- Adapt your approach based on intermediate results
- If blocked, explain what's blocking you and what you've tried

Available tools: read_file, execute_command, list_files, list_dir, search_in_files, 
grep_file, find_files, replace_in_file, tavily_search, read_url, read_lark_document,
multiply, add, divide.

Complete the task and return a clear summary of what was done and the results.""",
}

# ============================================================
# Subagent 可用工具 —— 除 browser / skill / plan / subagent 之外的全部工具
# ============================================================

_subagent_tools_cache = None

# 需要用 ainvoke 调用的异步工具名
_SUBAGENT_ASYNC_TOOLS = {
    "tavily_search", "read_url", "execute_command", "read_lark_document",
}


def _get_subagent_tools():
    """获取 subagent 可用的完整工具列表（排除 browser、skill、plan、subagent 工具，带缓存）"""
    global _subagent_tools_cache
    if _subagent_tools_cache is not None:
        return _subagent_tools_cache

    from tools.execute_command_tool import execute_command
    from tools.file_tools import (
        read_file, list_files, list_dir, find_files,
        grep_file, search_in_files,
    )
    from tools.search_tool import tavily_search, read_url
    from tools.lark_tools import read_lark_document
    from tools.math_tools import multiply, add, divide

    _subagent_tools_cache = [
        # 命令执行
        execute_command,
        # 文件操作
        read_file, list_files,
        grep_file,
        # 搜索 & 网络
        tavily_search, read_url,
        # 飞书文档
        read_lark_document,
        # 数学
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
MAX_SUBAGENT_ITERATIONS = 120


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
    """

    # --------------------------------------------------
    # Node 1: llm_call —— 模型推理节点
    # --------------------------------------------------
    async def _subagent_llm_call(state: SubagentState):
        """Subagent 的 LLM 调用节点（对标主 agent 的 llm_call）"""
        msgs = state["messages"]
        try:
            response = await model_with_tools.ainvoke(msgs)
            return {
                "messages": [response],
                "llm_calls": state.get("llm_calls", 0) + 1,
            }
        except Exception as e:
            error_msg = f"Subagent LLM error: {type(e).__name__}: {e}"
            console.print(f"[red]{error_msg}[/red]")
            return {
                "messages": [AIMessage(content=error_msg)],
                "llm_calls": state.get("llm_calls", 0) + 1,
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
            try:
                t = tools_by_name[tool_name]
                if tool_name in _SUBAGENT_ASYNC_TOOLS:
                    observation = await t.ainvoke(tool_call["args"])
                else:
                    observation = t.invoke(tool_call["args"])
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
        """
        对标主 agent 的 should_continue：
        - 有 tool_calls → tool_node
        - 无 tool_calls 或 超过最大迭代 → END
        """
        messages = state["messages"]
        last_message = messages[-1]

        # 超过最大迭代次数，强制结束
        if state.get("llm_calls", 0) > MAX_SUBAGENT_ITERATIONS:
            console.print(f"[yellow]⚠️ Subagent 达到最大迭代次数 {MAX_SUBAGENT_ITERATIONS}，强制结束[/yellow]")
            return END

        # 有工具调用 → 执行工具
        if last_message.tool_calls:
            return "tool_node"

        # 无工具调用 → 结束
        return END

    # --------------------------------------------------
    # Edge 2: should_continue_from_tool —— tool_node 后判断
    # --------------------------------------------------
    def _should_continue_from_tool(state: SubagentState) -> Literal["llm_call", END]:
        """
        对标主 agent 的 should_continue_from_tool：
        - 正常情况 → 回到 llm_call 继续推理
        - 超过最大迭代 → END
        """
        if state.get("llm_calls", 0) > MAX_SUBAGENT_ITERATIONS:
            console.print(f"[yellow]⚠️ Subagent 达到最大迭代次数 {MAX_SUBAGENT_ITERATIONS}，强制结束[/yellow]")
            return END

        return "llm_call"

    # --------------------------------------------------
    # 组装 Graph —— 完全对标主 agent
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


def _get_or_build_subagent(model_with_tools):
    """获取或构建 subagent graph 实例（单例缓存）"""
    global _subagent_instance
    if _subagent_instance is None:
        _subagent_instance = _build_subagent(model_with_tools)
    return _subagent_instance


def reset_subagent_cache():
    """清除所有缓存的 subagent。在模型切换或重置会话时调用。"""
    global _subagent_instance, _subagent_tools_cache
    _subagent_instance = None
    _subagent_tools_cache = None
    console.print("[dim]🧹 Subagent 缓存已清除[/dim]")


# ============================================================
# Subagent 调度工具（异步版本）
# ============================================================

@tool
async def dispatch_subagent(
        task: str,
        subagent_type: Optional[str] = None,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
) -> str:
    """
    派遣一个专门的子代理 (subagent) 来独立完成一个子任务。

    当你有多个独立的子任务需要并行处理，或者某个任务需要专门的关注时，
    使用此工具将任务分派给子代理。你可以在单轮中同时调用多个 dispatch_subagent
    来并行执行多个子任务（LangGraph 自动并行执行所有 tool_calls）。

    ## 两种使用模式

    ### 模式 1: 指定 subagent_type（使用预定义类型）
    传入 subagent_type 选择预定义类型，system_prompt 可选（不提供则使用默认）：
    - "code-explorer": 代码探索专家，搜索、阅读、分析代码，不修改文件
    - "code-writer": 代码编写专家，编写和修改代码文件
    - "researcher": 网络研究专家，搜索网页、阅读页面、综合信息
    - "general": 通用任务专家，执行各类任务

    ### 模式 2: 完全自定义（不指定 subagent_type）
    subagent_type 为空时，必须提供 system_prompt。
    你可以完全自定义子代理的角色、行为、约束和输出格式。
    这适用于预定义类型无法覆盖的特殊场景。

    ## ⭐ system_prompt 编写指南
    好的 system_prompt 是提升子代理执行效果的关键，应包含：
    1. 角色定义：子代理是什么专家，要完成什么使命
    2. 约束条件：明确边界（只读不写、只改特定文件、不要构建等）
    3. 输出格式：指定期望的报告格式（表格、列表、结构化报告等）
    4. 上下文信息：文件路径、命名规范、技术栈、依赖关系等
    5. 工具指引：优先使用哪些工具、避免哪些陷阱

    示例 system_prompt：
    "你是 React 组件分析专家。分析 src/components/ 下所有组件的
    props 接口定义，找出未使用的 props。只读不写。表格输出：组件名、未使用 props、建议。"

    重要提示：
    - 子代理独立运行，拥有自己的工具和推理循环
    - 子代理之间不能直接通信，所有协调由你（主代理）完成
    - 子代理返回结果后，你需要综合所有结果向用户汇报
    - 适合并行分派的场景：同时研究多个主题、同时探索多个模块、同时编写多个独立文件
    - 每个子代理有 120 秒超时限制和 15 轮推理限制

    Args:
        task: 要分配给子代理的具体任务描述，越详细越好
        subagent_type: 可选，子代理类型。为空时必须提供 system_prompt。
                       可选值: "code-explorer", "code-writer", "researcher", "general"
        system_prompt: 可选，自定义子代理的系统提示词。subagent_type 为空时必填。
                       应包含角色定义、具体约束、输出格式等完整指令。
        context: 可选，为子代理提供额外的背景信息（如相关文件路径、项目约定等）

    Returns:
        子代理完成任务的完整报告
    """
    import qoze_code_agent

    # ---- 参数校验 ----

    if subagent_type is not None:
        subagent_type = subagent_type.strip()
        if not subagent_type:
            subagent_type = None

    if system_prompt is not None:
        system_prompt = system_prompt.strip()
        if not system_prompt:
            system_prompt = None

    if not subagent_type and not system_prompt:
        return (
            "❌ 参数错误：subagent_type 和 system_prompt 不能同时为空。\n"
            "请至少提供其中之一：\n"
            "- 传入 subagent_type 使用预定义类型（system_prompt 可选）\n"
            f"  可用类型: {', '.join(SUBAGENT_TYPE_PROMPTS.keys())}\n"
            "- 或者不指定 subagent_type，但必须提供 system_prompt 来完全自定义子代理"
        )

    if subagent_type and subagent_type not in SUBAGENT_TYPE_PROMPTS:
        valid_types = ", ".join(SUBAGENT_TYPE_PROMPTS.keys())
        return (
            f"❌ 未知的子代理类型 '{subagent_type}'。\n"
            f"可用类型: {valid_types}\n"
            f"或者不指定 subagent_type，通过 system_prompt 完全自定义。"
        )

    # ---- 获取模型 ----

    llm_with_tools = qoze_code_agent.llm_with_tools
    if llm_with_tools is None:
        return "❌ Subagent 无法初始化：主 agent 的 LLM 尚未就绪，请稍后重试。"

    try:
        subagent = _get_or_build_subagent(llm_with_tools)

        effective_system_prompt = system_prompt or SUBAGENT_TYPE_PROMPTS[subagent_type]

        user_content = f"## Task\n{task}"
        if context:
            user_content += f"\n\n## Additional Context\n{context}"
        user_content += "\n\nComplete the task and return a clear summary of what you did and the results."

        messages = [
            SystemMessage(content=effective_system_prompt),
            HumanMessage(content=user_content),
        ]

        # 执行 subagent，带超时
        result = await asyncio.wait_for(
            subagent.ainvoke({"messages": messages, "llm_calls": 0}),
            timeout=600.0
        )

        result_messages = result.get("messages", [])
        if not result_messages:
            return "⚠️ Subagent 完成但没有返回任何消息。"

        final_response = ""
        for msg in reversed(result_messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_response = msg.content
                break

        if not final_response:
            final_response = (
                str(result_messages[-1].content)
                if result_messages[-1].content
                else "Subagent 执行完成（无文本输出）"
            )

        # 统计
        total_llm_calls = result.get("llm_calls", 0)
        ai_count = sum(1 for m in result_messages if isinstance(m, AIMessage))
        tool_count = sum(1 for m in result_messages if isinstance(m, ToolMessage))
        stats = f"\n\n---\n📊 Subagent 统计: {ai_count} 轮推理, {tool_count} 次工具调用, {total_llm_calls} 次 LLM 调用"

        return final_response + stats

    except asyncio.TimeoutError:
        return "⚠️ Subagent 执行超时（120秒），任务可能过于复杂。请尝试拆分为更小的子任务。"
    except Exception as e:
        traceback.print_exc()
        return f"❌ Subagent 执行失败: {type(e).__name__}: {e}"
