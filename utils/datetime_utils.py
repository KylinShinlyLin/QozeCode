#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日期时间工具模块 - 提供可信的当前系统时间基准

背景:
    LLM 训练数据存在时间截点，Agent 容易把"当前日期"幻觉为过去的日期
    （例如用旧年份构造搜索关键词）。本模块直接读取当前电脑系统时间，
    为动态上下文注入和 Agent 工具调用提供统一的时间基准。
"""
from datetime import datetime

_WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
_WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _now() -> datetime:
    """获取带本地时区信息的当前时间"""
    return datetime.now().astimezone()


def _utc_offset_text(dt: datetime) -> str:
    """将 +0800 格式的时区偏移格式化为 UTC+08:00"""
    offset = dt.strftime("%z")
    if not offset:
        return "UTC"
    return f"UTC{offset[:3]}:{offset[3:]}"


def get_current_time_text() -> str:
    """
    获取单行当前时间描述（用于注入系统提示词动态上下文）

    Returns:
        str: 如 "2026-07-19 14:30:25 星期六 (UTC+08:00)"
    """
    now = _now()
    return f"{now.strftime('%Y-%m-%d %H:%M:%S')} {_WEEKDAYS_CN[now.weekday()]} ({_utc_offset_text(now)})"


def get_current_datetime_detail() -> str:
    """
    获取多行详细当前时间信息（用于 Agent 工具返回）

    Returns:
        str: 包含日期、时间、星期、时区、ISO 8601 和 Unix 时间戳的格式化文本
    """
    now = _now()
    return "\n".join([
        f"当前系统时间: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"星期: {_WEEKDAYS_CN[now.weekday()]} ({_WEEKDAYS_EN[now.weekday()]})",
        f"时区: {now.tzname() or '本地时区'} ({_utc_offset_text(now)})",
        f"ISO 8601: {now.isoformat()}",
        f"Unix 时间戳: {int(now.timestamp())}",
    ])
