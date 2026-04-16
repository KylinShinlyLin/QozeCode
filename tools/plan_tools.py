#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plan 模式相关工具
"""
from langchain_core.tools import tool
from plan.plan_manager import PlanManager


@tool
def update_plan_progress(task_id: str, status: str) -> str:
    """
    更新计划任务状态。在执行计划过程中调用，标记任务进度。

    Args:
        task_id: 任务ID，如 "task_01"
        status: 任务状态，可选值: "pending"(待开始), "in_progress"(进行中), "done"(已完成)

    Returns:
        更新结果提示
    """
    manager = PlanManager()
    if not manager.has_valid_plan():
        return "当前没有有效计划，无法更新进度。"

    success = manager.update_task_status(task_id, status)
    if success:
        return f"✓ 任务 {task_id} 状态已更新为 {status}"
    else:
        return f"✗ 任务 {task_id} 更新失败，请检查 task_id 是否正确。"
