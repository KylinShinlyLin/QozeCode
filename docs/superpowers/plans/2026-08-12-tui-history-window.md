# TUI History Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前进程内长会话的 Textual Widget 数量限制在稳定范围，同时保留完整 LangGraph 上下文和可分页查看的 UI 历史。

**Architecture:** MessageList 维护轻量 `RenderedTurnRecord` 模型和有限 live turn 窗口；离开窗口的 Widget 被卸载但记录保留，用户按页加载时由记录重新创建只读 Widget。模型 checkpoint 与 UI archive 完全分离。

**Tech Stack:** Python 3.10+、Textual、dataclasses、pytest

## Global Constraints

- 仅在 TUI stream P0/P1/P2 验证通过后执行本计划。
- 默认 live 窗口 24 轮，分页大小 12 轮。
- 卸载 UI Widget 不得删除或修改 LangGraph/checkpointer 消息。
- 流式中的当前轮永不归档。
- 不新增第三方依赖。
- 未经用户确认不得运行测试、项目或构建；不得自动提交 Git。

---

## File Map

- Create `tui_components/messages/history_window.py`: 轮次记录、窗口选择、分页策略。
- Create `tui_components/messages/history_widgets.py`: 历史折叠条和轻量只读重建组件。
- Modify `tui_components/messages/message_list.py`: 轮次生命周期、归档、加载和滚动锚点。
- Modify `tui_components/messages/{user_widget,bot_widget,thinking_widget}.py`: 导出轻量 archive payload。
- Create `tests/tui/test_history_window.py`、`test_message_archiving.py`。

### Task 1: 纯 HistoryWindow 策略

**Files:**
- Create: `tui_components/messages/history_window.py`
- Test: `tests/tui/test_history_window.py`

**Interfaces:**
- Produces: `ArchivedMessage(kind, text, metadata)`、`RenderedTurnRecord(id, messages, live_widgets, finalized)`、`HistoryWindow(max_live_turns=24, page_size=12)`；方法 `start_turn()`、`append_message()`、`finalize_turn()`、`turns_to_archive()`、`previous_page()`。

- [ ] 写失败测试：不足 24 轮不归档；第 25 轮完成后只归档最旧完成轮；当前流式轮不归档；previous_page 每次返回最多 12 轮且顺序正确。
- [ ] 经授权运行确认失败。
- [ ] 实现纯数据策略，不导入 Textual，便于独立测试。
- [ ] 增加 clear/reset 和边界测试后运行通过。
- [ ] diff 自检并等待提交授权。

### Task 2: Widget archive payload

**Files:**
- Modify: `tui_components/messages/user_widget.py`
- Modify: `tui_components/messages/bot_widget.py`
- Modify: `tui_components/messages/thinking_widget.py`
- Modify: `tui_components/messages/message_list.py`
- Test: `tests/tui/test_message_archiving.py`

**Interfaces:**
- Produces: 每种 Widget 的 `to_archive_message() -> ArchivedMessage`；工具结果由 MessageList 构造 payload。

- [ ] 写失败测试：用户、AI、thinking、工具摘要导出后文本完整，metadata 只含重建所需字段，不持有 Widget/App 引用。
- [ ] 经授权运行确认失败。
- [ ] 实现 payload；AI 保存最终 raw Markdown，thinking 保存折叠正文，工具保存 display/status/elapsed。
- [ ] 运行测试并用弱引用检查 archive 后记录不阻止 Widget 回收。
- [ ] diff 自检并等待提交授权。

### Task 3: 轻量历史重建组件

**Files:**
- Create: `tui_components/messages/history_widgets.py`
- Test: `tests/tui/test_message_archiving.py`

**Interfaces:**
- Produces: `HistoryBoundaryWidget(hidden_turns, on_load)`；`ArchivedTurnWidget(record, expanded=False)`。

- [ ] 写失败测试：边界条显示隐藏轮数；归档轮默认折叠；展开时才创建 Markdown；再次折叠释放 Markdown 子树并保留 payload。
- [ ] 经授权运行确认失败。
- [ ] 使用 Static header + 按需 mount/remove 内容，禁止初始化时为每条历史创建隐藏 Markdown。
- [ ] 运行测试并检查选择复制仍使用现有 AutoCopy 组件。
- [ ] diff 自检并等待提交授权。

### Task 4: MessageList 轮次生命周期与自动归档

**Files:**
- Modify: `tui_components/messages/message_list.py`
- Test: `tests/tui/test_message_archiving.py`

**Interfaces:**
- Consumes: `HistoryWindow` 和 archive payload。
- Produces: `begin_rendered_turn(user_widget)`、`finalize_rendered_turn()`、`archive_old_turns()`。

- [ ] 写失败测试：用户消息开始新轮；正文/thinking/tool/subagent 归属当前轮；stream 完成后 finalize；超过 24 轮只卸载最旧完成轮。
- [ ] 经授权运行确认失败。
- [ ] 在现有 add/mount 回调处登记 Widget；归档前生成 payload，再异步 remove live widgets。
- [ ] 插入单个 HistoryBoundaryWidget，不为每个归档轮保留边界 Widget。
- [ ] clear_messages 同时清空 window、archive 和 subagent 映射。
- [ ] 运行测试并检查当前流式轮绝不被卸载。
- [ ] diff 自检并等待提交授权。

### Task 5: 分页加载与滚动锚点

**Files:**
- Modify: `tui_components/messages/message_list.py`
- Modify: `tui_components/messages/history_widgets.py`
- Test: `tests/tui/test_message_archiving.py`

**Interfaces:**
- Produces: `load_previous_history_page()`，每页 12 轮。

- [ ] 写失败测试：加载上一页后当前可见内容不跳到底部；记录加载前 boundary 下方锚点偏移并在 mount 后补偿 scroll_y；连续加载顺序正确。
- [ ] 经授权运行确认失败。
- [ ] 在 boundary 后批量 mount `ArchivedTurnWidget`，一次性请求结构布局，恢复滚动锚点。
- [ ] 用户回到底部后仍只恢复 SSE auto-follow，不自动卸载正在阅读的历史页；下一轮开始时按预算重新收敛。
- [ ] 运行测试并验证 PageUp/End 行为。
- [ ] diff 自检并等待提交授权。

### Task 6: 长会话验证门

- [ ] 经授权运行历史窗口定向测试和 TUI 全量测试。
- [ ] 经授权运行 20/50/100 轮模拟，记录直接子 Widget、Markdown 子树数量、滚动 P95 和内存趋势。
- [ ] 人工验证超长 Markdown、thinking、工具、Subagent、选择复制、加载上一页、clear。
- [ ] 确认 LangGraph state 中消息数量在 UI 归档前后完全一致。
- [ ] 对照目标：100 轮时 live 完整轮不超过 24，滚动成本不超过初始约 2 倍。
- [ ] 展示 diff、指标和回归结果；是否提交由用户决定。
