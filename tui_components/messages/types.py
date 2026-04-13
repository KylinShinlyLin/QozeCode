# tui_components/messages/types.py
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


class MessageType(Enum):
    """消息类型枚举"""
    USER = auto()
    BOT = auto()
    TOOL = auto()


class ToolStatus(Enum):
    """工具执行状态"""
    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    ERROR = auto()


@dataclass
class UserMessage:
    """用户消息体"""
    id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    is_command: bool = False
    attachments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BotMessage:
    """AI 回复消息体"""
    id: str
    thinking_content: str = ""
    content: str = ""
    is_streaming: bool = False
    thinking_complete: bool = False
    model_name: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    token_count: Optional[int] = None


@dataclass
class ToolMessage:
    """工具消息体"""
    id: str
    tool_name: str
    tool_args: Dict[str, Any]
    tool_call_id: str
    display_name: str = ""
    status: ToolStatus = ToolStatus.PENDING
    result_content: str = ""
    error_message: Optional[str] = None
    elapsed_time: float = 0.0
    start_time: datetime = field(default_factory=datetime.now)
    timestamp: datetime = field(default_factory=datetime.now)
