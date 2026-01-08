#!/usr/bin/env python3
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
import os
import platform
import socket
import traceback
from typing import Literal, List
from langchain_core.messages import AnyMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict, Annotated
from shared_console import console
from tools.execute_command_tool import execute_command
from tools.search_tool import tavily_search, get_webpage_to_markdown
from utils.directory_tree import get_directory_tree
from utils.system_prompt import get_system_prompt

os.environ.setdefault('ABSL_LOGGING_VERBOSITY', '1')  # 只显示 WARNING 及以上级别
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')  # 屏蔽 TensorFlow 信息和警告

# 定义颜色常量
CYAN = "\033[96m"
RESET = "\033[0m"

# 全局 LLM 变量，将在 main 函数中初始化
llm = None
llm_with_tools = None
browser_tools = None

base_tools = [execute_command, tavily_search, get_webpage_to_markdown]

# 初始时不加载浏览器工具
tools = base_tools
browser_loaded = False
plan_mode = False
# 当前会话
conversation_state = {"messages": [], "llm_calls": 0}

tools_by_name = {tool.name: tool for tool in tools}


# Step 1: Define state
class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int


# Step 2: Define model node
def llm_call(state: dict):
    system_release = ''
    system_info = platform.system()
    system_version = "unknown"
    current_dir = os.getcwd()
    username = os.getenv('USER', 'unknown')
    hostname = socket.gethostname()

    shell = home_dir = "unknown"
    machine_type = processor = "unknown"
    directory_tree = "无法获取目录结构"
    # 获取系统信息
    try:
        # 基本系统信息
        system_info = platform.system()
        system_version = platform.version()
        system_release = platform.release()
        machine_type = platform.machine()
        processor = platform.processor()
        # 当前工作目录
        current_dir = os.getcwd()
        # 用户信息
        username = os.getenv('USER') or os.getenv('USERNAME') or 'unknown'
        # 主机名
        hostname = socket.gethostname()
        # 环境变量中的重要信息
        shell = os.getenv('SHELL', 'unknown')
        home_dir = os.getenv('HOME', 'unknown')
        directory_tree = get_directory_tree(current_dir)

    except Exception:
        print("获取设备信息异常")

    system_msg = get_system_prompt(system_info=system_info, system_release=system_release,
                                   system_version=system_version, machine_type=machine_type, processor=processor,
                                   hostname=hostname, username=username, shell=shell, current_dir=current_dir,
                                   home_dir=home_dir, directory_tree=directory_tree, plan_mode=plan_mode)

    return {
        "messages": [
            llm_with_tools.invoke(
                [
                    SystemMessage(
                        content=system_msg
                    )
                ]
                + state["messages"]
            )
        ],
        "llm_calls": state.get('llm_calls', 0) + 1
    }


# Step 3: Define tool node
async def tool_node(state: dict):
    """Performs the tool call"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        try:
            # 检查是否是异步工具
            if tool_call["name"] in ["tavily_search", "get_webpage_to_markdown"]:
                observation = await tool.ainvoke(tool_call["args"])
            else:
                observation = tool.invoke(tool_call["args"])
            result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
        except Exception as e:
            traceback.print_exc()
            error_msg = f"  ❌ '{tool_call['name']}' 调用失败，错误信息:{e}"
            console.print(error_msg, style="red")
            result.append(ToolMessage(content=error_msg, tool_call_id=tool_call["id"]))
    return {"messages": result}


# Step 4: Define logic to determine whether to end
def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]
    # If the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "tool_node"
    return END


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
agent_builder.add_edge("tool_node", "llm_call")

# Compile the agent
agent = agent_builder.compile()


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


def create_message_with_images(text_content: str, image_folder: str = ".qoze/image") -> HumanMessage:
    """创建包含文本和图片的消息"""
    # 基础消息内容
    message_content = [{"type": "text", "text": text_content}]

    # 检查图片文件夹
    if os.path.exists(image_folder):
        image_files = get_image_files(image_folder)

        if image_files:
            # 添加图片到消息内容
            for image_path in image_files[:5]:  # 限制最多5张图片，避免请求过大
                base64_data = image_to_base64(image_path)
                if base64_data:
                    # 获取图片文件名用于标识
                    image_name = os.path.basename(image_path)
                    # 添加图片数据
                    message_content.append({
                        "mime_type": "image/jpeg",
                        "type": "image",
                        "source_type": "base64",
                        "data": base64_data
                    })

            if len(image_files) > 5:
                console.print(f"⚠️  图片数量超过5张，只发送前5张", style="yellow")

    return HumanMessage(content=message_content)
