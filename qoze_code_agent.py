from langgraph.checkpoint.memory import MemorySaver

# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright 2025 QozeCode

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import base64
import operator
import platform
import traceback
from typing import Literal, List
from langchain_core.messages import AnyMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict, Annotated
from shared_console import console
import sys
import os

from tools.execute_command_tool import execute_command
from tools.file_tools import read_file, list_files, search_in_files, cat_file, list_dir, file_stats, grep_file, \
    find_files

sys.path.append(os.path.join(os.path.dirname(__file__), '.qoze'))
from tools.search_tool import tavily_search, read_url
from tools.browser_tool import browser_navigate, browser_click, browser_type, browser_read_page, \
    browser_get_html, browser_close, browser_scroll, browser_open_tab, browser_switch_tab, browser_list_tabs
from tools.skill_tools import activate_skill, list_available_skills, deactivate_skill, get_skill_install_guide
from tools.lark_tools import read_lark_document
from tools.common_tools import ask_for_user
from skills.skill_manager import SkillManager
from utils.directory_tree import get_directory_tree
from utils.system_prompt import get_static_system_prompt, get_dynamic_context

os.environ.setdefault('ABSL_LOGGING_VERBOSITY', '1')  # 只显示 WARNING 及以上级别
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')  # 屏蔽 TensorFlow 信息和警告

# 定义颜色常量
CYAN = "\033[96m"
RESET = "\033[0m"

# 全局技能管理器
skill_manager = None


def load_qoze_rules(current_dir):
    """
    加载 .qoze/rules 目录下的自定义规则文件
    
    Args:
        current_dir: 当前工作目录
        
    Returns:
        str: 格式化的规则内容，如果没有规则则返回空字符串
    """
    rules_dir = os.path.join(current_dir, '.qoze', 'rules')
    rules_prompt = ''

    if os.path.exists(rules_dir) and os.path.isdir(rules_dir):
        try:
            # 获取目录中的所有文件
            rule_files = [f for f in os.listdir(rules_dir) if os.path.isfile(os.path.join(rules_dir, f))]

            if rule_files:
                rules_prompt += "## 当前自定义 agent 规则\n"
                for file_name in sorted(rule_files):  # 按文件名排序
                    file_path = os.path.join(rules_dir, file_name)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                        rules_prompt += f"### {file_name}\n{file_content}\n"
                    except Exception:
                        pass  # 静默处理单个文件读取错误
                rules_prompt += "\n"

        except Exception:
            pass  # 静默处理目录读取错误

    return rules_prompt


def get_context_info(system_info="", system_release="", system_version="", machine_type="", processor="",
                     shell="", current_dir="", directory_tree=""):
    """
    获取上下文信息（分离静态和动态内容以优化 Prompt Caching）

    Returns:
        tuple: (static_system_prompt, dynamic_context)
               - static_system_prompt: 可被缓存的静态 System Prompt
               - dynamic_context: 每次变化的动态上下文
    """
    # 兼容 ~/.qoze/skills 下的脚本调用
    user_qoze_path = os.path.expanduser("~/.qoze")
    if user_qoze_path not in sys.path:
        sys.path.append(user_qoze_path)

    global skill_manager
    if skill_manager is None:
        skill_manager = SkillManager()

    # 获取静态 System Prompt（可被 OpenAI Prompt Caching 缓存）
    static_prompt = get_static_system_prompt()

    # 加载自定义规则（放在动态上下文中，避免影响 System Prompt 缓存）
    rules_prompt = load_qoze_rules(current_dir)

    # 获取技能信息
    available_skills = skill_manager.get_available_skills()
    active_skills_content = skill_manager.get_active_skills_content()

    # 构建动态上下文（放在 User Message 中，避免影响 System Prompt 缓存）
    dynamic_context = get_dynamic_context(
        system_info=system_info,
        system_release=system_release,
        system_version=system_version,
        machine_type=machine_type,
        processor=processor,
        shell=shell,
        current_dir=current_dir,
        directory_tree=directory_tree,
        rules_prompt=rules_prompt,
        available_skills=available_skills,
        active_skills_content=active_skills_content
    )

    return static_prompt, dynamic_context


# 保留向后兼容的函数名
def get_enhanced_system_prompt(system_info="", system_release="", system_version="", machine_type="", processor="",
                               shell="", current_dir="", directory_tree=""):
    """【向后兼容】获取完整的系统提示词"""
    static, dynamic = get_context_info(system_info, system_release, system_version, machine_type,
                                       processor, shell, current_dir, directory_tree)
    return static + "\n" + dynamic


# 全局 LLM 变量，将在 main 函数中初始化
llm = None
llm_with_tools = None
browser_tools = None

base_tools = [
    execute_command,
    tavily_search,
    read_url,
    activate_skill,
    list_available_skills,
    deactivate_skill,
    get_skill_install_guide,
    read_file,
    # list_files,
    # search_in_files,
    cat_file,
    # list_dir,
    # file_stats,
    # grep_file,
    # find_files,
    browser_navigate,
    browser_click,
    browser_type,
    browser_read_page,
    browser_get_html,
    browser_close,
    browser_scroll,
    browser_open_tab,
    browser_switch_tab,
    browser_list_tabs,
    read_lark_document,
    ask_for_user,
]

# 初始时不加载浏览器工具
tools = base_tools
browser_loaded = False
plan_mode = False
conversation_state = {"llm_calls": 0, "last_image_count": 0, "sent_images": {}}

tools_by_name = {tool.name: tool for tool in tools}


# Step 1: Define state
class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
    ask_user_question: str  # 如果需要询问用户，存储问题内容


# Step 2: Define model node
async def llm_call(state: dict):
    import asyncio
    system_release = ''
    system_info = platform.system()
    system_version = "unknown"
    current_dir = os.getcwd()

    shell = "unknown"
    machine_type = processor = "unknown"
    directory_tree = "无法获取目录结构"
    try:
        system_info = platform.system()
        system_version = platform.version()
        system_release = platform.release()
        machine_type = platform.machine()
        processor = platform.processor()
        current_dir = os.getcwd()
        shell = os.getenv('SHELL', 'unknown')
        # Run directory tree generation in a thread to avoid blocking
        directory_tree = await asyncio.to_thread(get_directory_tree, current_dir)

    except Exception:
        print("获取设备信息异常")

    # 分离静态和动态内容以优化 Prompt Caching
    static_prompt, dynamic_context = get_context_info(
        system_info=system_info,
        system_release=system_release,
        system_version=system_version,
        machine_type=machine_type,
        processor=processor,
        shell=shell,
        current_dir=current_dir,
        directory_tree=directory_tree
    )

    # 构造消息：SystemMessage 放静态内容（可被缓存），UserMessage 放动态上下文
    messages = [SystemMessage(content=static_prompt)]

    # 将动态上下文作为第一条用户消息（或合并到现有用户消息中）
    if state["messages"]:
        # 如果已有消息，将动态上下文添加到第一条用户消息前面
        first_msg = state["messages"][0]
        if isinstance(first_msg, HumanMessage):
            # 如果是 HumanMessage，合并内容
            if isinstance(first_msg.content, str):
                combined_content = f"{dynamic_context}\n\n---\n\n{first_msg.content}"
                messages.append(HumanMessage(content=combined_content))
            else:
                # 内容可能是列表（多模态消息）
                messages.append(HumanMessage(content=dynamic_context))
                messages.append(first_msg)
        else:
            messages.append(HumanMessage(content=dynamic_context))
            messages.append(first_msg)
        # 添加剩余消息
        messages.extend(state["messages"][1:])
    else:
        messages.append(HumanMessage(content=dynamic_context))

    response = await llm_with_tools.ainvoke(messages)

    return {
        "messages": [response],
        "llm_calls": state.get('llm_calls', 0) + 1,
        "ask_user_question": None  # 重置 ask_user_question
    }


# Step 3: Define tool node
async def tool_node(state: dict):
    """Performs the tool call"""

    result = []
    ask_question = None

    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        try:
            # 检查是否是异步工具
            if tool_call["name"] in ["tavily_search", "read_url", "execute_command", "browser_navigate",
                                     "browser_click", "browser_type", "browser_read_page", "browser_screenshot",
                                     "browser_get_html", "browser_close", "browser_scroll", "browser_open_tab",
                                     "browser_switch_tab", "browser_list_tabs"]:
                observation = await tool.ainvoke(tool_call["args"])
            else:
                observation = tool.invoke(tool_call["args"])
            result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"], name=tool_call["name"]))

            # 如果调用了 ask_for_user，提取问题
            if tool_call["name"] == "ask_for_user":
                ask_question = tool_call["args"].get("question", "")

        except Exception as e:
            traceback.print_exc()
            error_msg = f"  ❌ '{tool_call['name']}' 调用失败，错误信息:{e}"
            console.print(error_msg, style="red")
            result.append(ToolMessage(content=error_msg, tool_call_id=tool_call["id"], name=tool_call["name"]))

    return {"messages": result, "ask_user_question": ask_question}

# Step 4: Define logic to determine whether to end
def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]
    # If the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "tool_node"
    return END


def should_continue_from_tool(state: MessagesState) -> Literal["llm_call", END]:
    """从 tool_node 决定是回到 llm_call 还是结束（用于 ask_for_user）"""
    # 如果调用了 ask_for_user，直接结束等待用户输入
    if state.get("ask_user_question"):
        return END
    return "llm_call"

# Step 5: Build agent
# Build workflow
agent_builder = StateGraph(MessagesState)

# Add nodes
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

# Add edges to connect nodes
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    ["tool_node", END]
)
agent_builder.add_conditional_edges(
    "tool_node",
    should_continue_from_tool,
    ["llm_call", END]
)

# Compile the agent
memory = MemorySaver()
agent = agent_builder.compile(checkpointer=memory)


def get_image_files(folder_path: str) -> List[str]:
    """获取文件夹中的所有图片文件"""
    if not os.path.exists(folder_path):
        return []

    image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    image_files = []

    try:
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            if os.path.isfile(file_path):
                _, ext = os.path.splitext(file.lower())
                if ext in image_extensions:
                    image_files.append(file_path)
    except Exception as e:
        console.print(f"读取图片文件时出错: {str(e)}", style="red")

    return image_files


def image_to_base64(image_path: str) -> str:
    """将图片文件转换为base64编码"""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        console.print(f"转换图片 {image_path} 为base64时出错: {str(e)}", style="yellow")
        return None


def reset_conversation_state():
    """重置会话状态"""
    global conversation_state
    conversation_state["llm_calls"] = 0
    conversation_state["last_image_count"] = 0
    conversation_state["sent_images"] = {}


def estimate_token_count(messages: list, model: str = "gpt-4") -> int:
    """
    估算消息的 token 数量
    优先使用 tiktoken 进行精确计算，如果失败则使用字符估算
    """
    total_tokens = 0

    # 尝试使用 tiktoken 进行精确计算
    try:
        import tiktoken

        # 尝试获取对应模型的编码器
        try:
            encoding = tiktoken.encoding_for_model(model)
        except (KeyError, Exception):
            # 如果模型未识别或出错，使用 cl100k_base（适用于 GPT-4, GPT-3.5 等）
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                # tiktoken 初始化失败（如网络问题），回退到字符估算
                raise ImportError("tiktoken initialization failed")

        for msg in messages:
            if hasattr(msg, 'content'):
                content = msg.content

                # 计算消息内容的 token
                if isinstance(content, str):
                    tokens = encoding.encode(content)
                    total_tokens += len(tokens)
                elif isinstance(content, list):
                    # 多模态消息，计算文本部分
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            text = item.get('text', '')
                            tokens = encoding.encode(text)
                            total_tokens += len(tokens)

                # 每条消息有固定的开销（角色标记等）
                total_tokens += 4

        # 每次回复有固定的开销
        total_tokens += 3

        return total_tokens

    except (ImportError, Exception):
        # tiktoken 不可用或初始化失败，使用字符估算作为 fallback
        pass

    # Fallback：使用字符数估算
    total_chars = 0
    for msg in messages:
        if hasattr(msg, 'content'):
            content = msg.content
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        total_chars += len(item.get('text', ''))

    # 粗略估算：平均每个字符约 0.3 token
    return int(total_chars * 0.3)


def create_message_with_images(text_content: str, image_folder: str = ".qoze/image") -> HumanMessage:
    """创建包含文本和图片的消息"""
    # 基础消息内容
    message_content = [{"type": "text", "text": text_content}]

    image_count = 0

    # 获取已发送图片记录
    sent_images = conversation_state.get("sent_images", {})
    new_sent_images = sent_images.copy()

    # 检查图片文件夹
    if os.path.exists(image_folder):
        image_files = get_image_files(image_folder)

        if image_files:
            # 添加图片到消息内容
            for image_path in image_files[:5]:  # 限制最多5张图片，避免请求过大
                try:
                    # 获取文件修改时间作为指纹
                    mtime = os.path.getmtime(image_path)

                    # 检查是否已发送过且未修改
                    if image_path in sent_images and sent_images[image_path] == mtime:
                        continue

                    base64_data = image_to_base64(image_path)
                    if base64_data:
                        # 添加图片数据
                        message_content.append({
                            "mime_type": "image/jpeg",
                            "type": "image",
                            "source_type": "base64",
                            "data": base64_data
                        })
                        image_count += 1
                        # 更新发送记录
                        new_sent_images[image_path] = mtime
                except Exception as e:
                    console.print(f"处理图片 {image_path} 时出错: {str(e)}", style="yellow")

            if len(image_files) > 5:
                console.print(f"⚠️  图片数量超过5张，只发送前5张", style="yellow")

    # 更新全局状态
    conversation_state["last_image_count"] = image_count
    conversation_state["sent_images"] = new_sent_images

    return HumanMessage(content=message_content)
