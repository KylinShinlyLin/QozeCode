#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plan 模式管理器
负责计划的检测、加载、解析、状态更新和清除
"""
import os
import re
import shutil
from typing import Optional


class PlanManager:
    PLAN_DIR = ".qoze/plan"
    FILES = {
        "understanding": "01_understanding.md",
        "design": "02_design.md",
        "tasks": "03_tasks.md",
    }

    _PROMPT_TEMPLATE = """{preamble}

## 能力边界（任务必须在此范围内）
Agent 能做的事：读/写项目文件、执行非交互式 Shell 命令、网络搜索、代码分析、在 `/.qoze/` 下写临时文件。
Agent 不能做的事（任务中严禁出现）：主动运行测试/构建/启动项目、不经确认安装依赖、使用交互式 UI、操作当前目录外内容、部署到外部系统或操作硬件。
超出边界的需求，应在 PLAN_UNDERSTANDING 中指出，并在 PLAN_DESIGN 中转化为 Agent 能做的等价动作。

## 输出格式要求
必须严格使用以下 XML 标签包裹内容。`PLAN_DESIGN` 必须是一份可直接落地的执行方案，每个章节都要具体到文件、函数、配置项级别，禁止写空泛建议。

<PLAN_UNDERSTANDING>
- 目标：一句话概括要做什么
- 边界：涉及哪些模块/文件，明确排除什么
- 关键挑战：最大的技术或逻辑难点
- 限制：哪些需求 Agent 无法直接执行，需要转化或用户介入
</PLAN_UNDERSTANDING>

<PLAN_DESIGN>
## 1. 整体思路
- 输入/现状：当前相关代码/配置的基线状态
- 输出/目标：改完后应达到的具体状态（包含函数签名、数据结构、配置项的预期形态）
- 核心策略：1-2句话说明最关键的改造路径

## 2. 关键决策
每个决策必须包含「选项 A / 选项 B → 最终选择 → 理由」。例如：
- 在 X 模块新增接口 vs 复用 Y 模块现有接口 → 选择复用 Y → 因为 X 和 Y 职责重复，复用可减少维护面
- 修改现有表结构 vs 新增扩展表 → 选择新增扩展表 → 因为原表数据量大，避免迁移风险

## 3. 文件级改动清单（必须精确到文件路径）
用表格输出，字段至少包含：

| 文件路径 | 改动类型 | 核心变动点 | 关联检查点 |
|----------|----------|------------|------------|
| `path/to/file.py` | 修改 | 函数 A 增加参数 B；返回值从 int 改为 dict | 检查调用方 C.py 和 D.py 是否需要同步 |
| `path/to/new_file.py` | 新增 | 实现 X 功能，暴露 Y 接口 | 需在 Z.py 中注册/引用 |

要求：
- 文件路径必须是相对路径，基于项目根目录
- "核心变动点" 必须具体到函数名、类名、配置 key、路由路径等
- "关联检查点" 必须列出因本次改动而需要同步检查的其他文件或模块

## 4. 接口/数据流/依赖变化（如有）
如果改动涉及接口出入参、数据库字段、配置文件格式、跨模块调用，必须在此说明：
- 变更前 vs 变更后的对比（可用表格或代码片段形式）
- 哪些上游/下游会受到影响
- 是否需要更新类型定义、校验规则、映射逻辑、文档注释

## 5. 执行步骤（与 PLAN_TASKS 一一对应）
编号列出。每一步必须是 Agent 能独立完成的单一动作，格式：
1. **动作**：具体做什么（如：读取 `config/manager.py` 确认配置读取逻辑）
2. **验证标准**：怎么确认这一步做对了（如：`config_manager.py` 中新增 `get_xxx()` 函数，返回类型为 str）

步骤与 task 的映射关系要清晰，后续 `PLAN_TASKS` 中的 `task_NN` 必须与此处的步骤编号一一对应。

## 6. 风险与回退
- 高风险文件/函数：列出改动后最容易出错的 2-5 个位置
- 风险描述：每个位置可能出现什么问题（如：类型不匹配、遗漏初始化、并发问题）
- 快速检查方法：如果执行结果异常，优先检查哪些日志、文件、断言或单元测试文件（只能写测试代码，不能运行）
</PLAN_DESIGN>

<PLAN_TASKS>
基于 `PLAN_DESIGN` 的"执行步骤"，逐条映射为具体的 Markdown 任务列表，必须一一对应：
- [ ] task_01: 步骤1的动作内容
- [ ] task_02: 步骤2的动作内容
- [ ] task_03: 步骤3的动作内容

每个任务必须满足：单一职责、可验证完成、不超出 Agent 能力边界、能直接对应到具体的文件修改或分析动作。
</PLAN_TASKS>
"""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.getcwd()
        self.plan_dir = os.path.join(self.base_dir, self.PLAN_DIR)

    def has_valid_plan(self) -> bool:
        """三份文件同时存在且非空"""
        for filename in self.FILES.values():
            filepath = os.path.join(self.plan_dir, filename)
            if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                return False
        return True

    def load_plan_context(self) -> str:
        """读取三份文件，拼接成动态上下文字符串"""
        context = "## 当前执行计划\n"
        for key in ["understanding", "design", "tasks"]:
            filename = self.FILES[key]
            filepath = os.path.join(self.plan_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                context += f"\n### {filename}\n{content}\n"
        return context

    def build_generation_prompt(self, user_request: str) -> str:
        """构造让 LLM 一次性输出三份文档的 prompt"""
        preamble = f"""请根据以下用户需求，生成三份计划文档。\n\n## 用户需求\n{user_request}"""
        return self._PROMPT_TEMPLATE.format(preamble=preamble)

    def build_regeneration_prompt(self, user_request: str, current_plan: str = "") -> str:
        """基于现有计划 + 调整描述，让 LLM 重新生成计划"""
        preamble = f"""请根据以下调整描述，重新生成三份计划文档。\n\n## 现有计划（供参考）\n{current_plan}\n\n## 调整描述\n{user_request}"""
        return self._PROMPT_TEMPLATE.format(preamble=preamble)

    def save_plan_from_response(self, response_text: str) -> bool:
        """解析 LLM 回复，拆分保存到三个文件"""
        os.makedirs(self.plan_dir, exist_ok=True)

        understanding = self._extract_tag(response_text, "PLAN_UNDERSTANDING")
        design = self._extract_tag(response_text, "PLAN_DESIGN")
        tasks = self._extract_tag(response_text, "PLAN_TASKS")

        if not all([understanding, design, tasks]):
            return False

        self._write_file(self.FILES["understanding"], understanding.strip())
        self._write_file(self.FILES["design"], design.strip())
        self._write_file(self.FILES["tasks"], tasks.strip())
        return True

    def _extract_tag(self, text: str, tag: str) -> Optional[str]:
        pattern = rf"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1) if match else None

    def _write_file(self, filename: str, content: str):
        filepath = os.path.join(self.plan_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def update_task_status(self, task_id: str, status: str) -> bool:
        """更新 03_tasks.md 中对应任务状态"""
        tasks_file = os.path.join(self.plan_dir, self.FILES["tasks"])
        if not os.path.exists(tasks_file):
            return False

        with open(tasks_file, "r", encoding="utf-8") as f:
            content = f.read()

        status_map = {
            "pending": "[ ]",
            "done": "[x]",
            "in_progress": "[/]",
            "completed": "[x]",
            "complete": "[x]",
            "started": "[/]",
        }
        checkbox = status_map.get(status.lower(), f"[{status}]")

        pattern = rf"(- \[.\]) ({re.escape(task_id)}:)"
        new_content = re.sub(pattern, f"- {checkbox} \\2", content)

        if new_content == content:
            return False

        with open(tasks_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True

    def clear_plan(self):
        """删除 .qoze/plan 目录"""
        if os.path.exists(self.plan_dir):
            shutil.rmtree(self.plan_dir)

    def get_status_summary(self) -> str:
        """获取计划状态摘要"""
        if not self.has_valid_plan():
            return "暂无有效计划"

        tasks_file = os.path.join(self.plan_dir, self.FILES["tasks"])
        with open(tasks_file, "r", encoding="utf-8") as f:
            content = f.read()

        total = len(re.findall(r"- \[(.)\]", content))
        done = len(re.findall(r"- \[x\]", content))
        in_progress = len(re.findall(r"- \[/\]", content))
        pending = total - done - in_progress

        return f"计划进度: {done}/{total} 完成, {in_progress} 进行中, {pending} 待开始"
