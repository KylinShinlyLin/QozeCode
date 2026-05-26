#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git 上下文提取工具
在每次 LLM 调用的动态上下文中自动注入 git 状态信息。

设计理念（参考 Codex CLI 的 git-utils crate）：
- 不依赖 Agent 自己执行 git status，而是系统自动提取并注入
- 轻量级：每次只提取摘要信息，避免 token 浪费
- 容错：不在 git 仓库中时静默返回空字符串
"""
import subprocess
import os
from typing import Optional


def _run_git(cmd: list[str], cwd: str, timeout: float = 5.0) -> Optional[str]:
    """安全执行 git 命令，失败返回 None"""
    try:
        result = subprocess.run(
            ["git"] + cmd,
            capture_output=True, text=True,
            cwd=cwd, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def _find_git_root(cwd: str) -> Optional[str]:
    """查找 git 仓库根目录"""
    # 先检查当前目录
    if os.path.isdir(os.path.join(cwd, ".git")):
        return cwd
    # 再尝试通过 git rev-parse 查找
    return _run_git(["rev-parse", "--show-toplevel"], cwd)


def get_git_context(current_dir: str = None) -> str:
    """
    提取当前目录的 git 上下文，用于注入动态 prompt。

    提取信息（按优先级）：
    1. 当前分支名
    2. 工作区状态（已修改/已暂存/未跟踪文件数量和列表）
    3. 最近 3 条 commit 摘要
    4. 与远程分支的同步状态（ahead/behind）

    Returns:
        格式化的 markdown 字符串，如果不在 git 仓库则返回空字符串。
    """
    cwd = current_dir or os.getcwd()
    
    root = _find_git_root(cwd)
    if not root:
        return ""
    
    parts = []
    
    # 1. 当前分支
    branch = _run_git(["branch", "--show-current"], cwd)
    if branch:
        parts.append(f"**当前分支**: `{branch}`")
    else:
        # 可能处于 detached HEAD
        head = _run_git(["rev-parse", "--short", "HEAD"], cwd)
        if head:
            parts.append(f"**HEAD**: `{head}` (detached)")
    
    # 2. 工作区状态
    short_status = _run_git(["status", "--short"], cwd)
    if short_status:
        lines = [l for l in short_status.split("\n") if l.strip()]
        staged = sum(1 for l in lines if l[0] in "MADRC")
        unstaged = sum(1 for l in lines if len(l) > 1 and l[1] in "MD")
        untracked = sum(1 for l in lines if l.startswith("??"))
        
        status_parts = []
        if staged: status_parts.append(f"{staged} 个已暂存")
        if unstaged: status_parts.append(f"{unstaged} 个已修改(未暂存)")
        if untracked: status_parts.append(f"{untracked} 个未跟踪")
        
        if status_parts:
            parts.append(f"**工作区状态**: {', '.join(status_parts)}")
        
        # 变更文件列表（限制 12 个，超出则截断）
        changed_files = [l[3:] for l in lines[:12]]
        if changed_files:
            files_str = "`, `".join(changed_files)
            if len(lines) > 12:
                files_str += f"` ...及其他 {len(lines) - 12} 个文件"
            parts.append(f"**变更文件**: `{files_str}`")
    else:
        parts.append("**工作区状态**: 干净（无变更）")
    
    # 3. 最近 3 条 commit
    log = _run_git([
        "log", "--oneline", "-3", "--format=%h %s (%ar)"
    ], cwd)
    if log:
        parts.append(f"\n**最近 3 次提交**:\n```\n{log}\n```")
    
    # 4. 与远程的同步状态
    if branch:
        ahead_behind = _run_git([
            "rev-list", "--left-right", "--count", f"origin/{branch}...{branch}"
        ], cwd)
        if ahead_behind:
            try:
                behind_str, ahead_str = ahead_behind.split("\t")
                ahead, behind = int(ahead_str), int(behind_str)
                if ahead > 0 and behind > 0:
                    parts.append(f"**远程同步**: ⚠️ 领先 {ahead} 提交, 落后 {behind} 提交（需先 pull 再 push）")
                elif ahead > 0:
                    parts.append(f"**远程同步**: 📤 领先 {ahead} 个提交（未推送）")
                elif behind > 0:
                    parts.append(f"**远程同步**: 📥 落后 {behind} 个提交（需要 pull）")
                else:
                    parts.append(f"**远程同步**: ✅ 与 `origin/{branch}` 一致")
            except (ValueError, IndexError):
                pass
    
    if not parts:
        return ""
    
    return "## 📋 Git 仓库状态\n" + "\n".join(f"- {p}" for p in parts) + "\n"


def get_git_diff_context(current_dir: str = None, max_files: int = 10) -> str:
    """
    获取当前未暂存的 diff 统计摘要。
    只在 Agent 需要了解"现在正在改什么"时调用，不注入每轮上下文。
    
    Returns:
        diff --stat 输出，限制文件数量。
    """
    cwd = current_dir or os.getcwd()
    
    root = _find_git_root(cwd)
    if not root:
        return ""
    
    # 优先显示未暂存的 diff
    diff_stat = _run_git(["diff", "--stat"], cwd)
    if not diff_stat:
        # 如果没有未暂存变更，显示已暂存的 diff
        diff_stat = _run_git(["diff", "--staged", "--stat"], cwd)
    
    if not diff_stat:
        return "**当前无未提交的变更。**"
    
    lines = diff_stat.strip().split("\n")
    if len(lines) > max_files + 1:
        summary = lines[-1]  # 最后一行是汇总统计
        file_lines = lines[:max_files]
        diff_stat = "\n".join(file_lines) + f"\n ...及其他 {len(lines) - max_files - 1} 个文件\n{summary}"
    
    return f"## 📝 当前变更摘要\n```\n{diff_stat}\n```\n"
