#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日期时间工具 - 暴露给 Agent 调用的系统时间工具
"""
from langchain_core.tools import tool

from utils.datetime_utils import get_current_datetime_detail


@tool
def get_current_datetime() -> str:
    """获取当前电脑系统的真实日期和时间。

    任何涉及时间的判断（如"今天"、"最新"、"最近"、"本周"、"今年"、新闻/资讯/
    版本发布等时效性查询、搜索关键词中的年份/日期）都必须以该工具返回的真实
    系统时间为准，严禁凭借模型训练记忆猜测当前日期。

    Returns:
        格式化的当前系统时间信息，包含日期、时间、星期、时区、ISO 8601 和 Unix 时间戳。
    """
    return get_current_datetime_detail()
