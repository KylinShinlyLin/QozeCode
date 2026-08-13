# TUI Stream Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保持 SSE 连续可感知的同时，消除刷新积压、逐 chunk layout 和完整文本重复净化，使 JetBrains 终端在流式期间仍可滚动交互。

**Architecture:** 将数据累积与 UI 绘制分离：纯异步 `StreamRenderScheduler` 提供单槽 latest-wins 调度，`IncrementalDisplayBuffer` 对新增 chunk 只净化一次，MessageList 根据滚动状态决定是否绘制。结构性布局与普通内容刷新分离。

**Tech Stack:** Python 3.10+、asyncio、Textual、Rich、pytest（仅测试代码；执行测试需用户授权）

## Global Constraints

- 不改变 LangGraph stream 顺序、取消传播和最终内容语义。
- Terminal/iTerm2 目标 15–20 FPS；JediTerm 目标 8–12 FPS。
- 同一流最多一个 pending flush；中间帧可合并，最终帧不可丢失。
- UI 忙时优先响应滚动和键盘。
- 不新增第三方依赖。
- 未经用户确认不得运行测试、项目或构建；不得自动提交 Git。

---

## File Map

- Create `tui_components/messages/stream_scheduler.py`: 单槽异步刷新调度器。
- Create `tui_components/messages/display_buffer.py`: 增量净化、原始/展示 buffer、尾部窗口。
- Create `utils/performance_metrics.py`: 默认关闭的聚合性能指标。
- Modify `tui_components/messages/stream_handler.py`: 接入 scheduler/buffer，统一 thinking 和正文刷新。
- Modify `tui_components/messages/message_list.py`: repaint/layout 分离、滚动暂停与恢复。
- Modify `tui_components/messages/bot_widget.py`: 接收已净化展示快照，不再扫描完整 raw buffer。
- Modify `tui_components/messages/thinking_widget.py`: header 和展开内容由统一 flush 驱动。
- Modify `tui_components/messages/subagent_widget.py`: 合并刷新并避免折叠内容更新。
- Modify `tui_components/messages/tool_status_panel.py`: 共享低频 ticker。
- Modify `tui_components/request_indicator.py`: 降低动画频率。
- Modify `tui_components/terminal_compat.py`: 暴露终端渲染 profile。
- Modify `qoze_tui.py`: 把滚动状态传给 MessageList。
- Create `tests/tui/test_stream_scheduler.py`、`test_display_buffer.py`、`test_stream_interaction.py`。

### Task 1: 聚合性能指标

**Files:**
- Create: `utils/performance_metrics.py`
- Test: `tests/tui/test_performance_metrics.py`

**Interfaces:**
- Produces: `PerfMetrics.enabled`, `increment(name, value=1)`, `observe(name, seconds)`, `snapshot(reset=False)`, `get_perf_metrics()`。

- [ ] 写失败测试：未设置 `QOZE_PERF_DEBUG` 时不保留样本；启用时正确计算 count、total、max，并可 reset。
- [ ] 经用户授权后运行：`pytest tests/tui/test_performance_metrics.py -q`，预期首次因模块不存在而失败。
- [ ] 实现线程安全、默认关闭的内存聚合器；禁止在 `increment/observe` 内同步写文件。
- [ ] 再次运行同一测试，预期通过。
- [ ] 使用 `git diff --check` 和 `git diff -- utils/performance_metrics.py tests/tui/test_performance_metrics.py` 自检；如需提交，停止并请求用户授权。

### Task 2: 终端刷新预算

**Files:**
- Modify: `tui_components/terminal_compat.py`
- Test: `tests/tui/test_terminal_profile.py`

**Interfaces:**
- Produces: immutable `TerminalRenderProfile(name: str, frame_interval: float, busy_interval: float, tail_chars: int, tail_lines: int)`；`get_terminal_render_profile(env: Mapping[str, str] | None = None)`。

- [ ] 写参数化失败测试：JediTerm 为 `0.10/0.166` 秒，默认终端为 `0.05/0.10` 秒；环境判断不修改现有 emoji 语义。
- [ ] 经授权运行目标测试确认失败。
- [ ] 实现 profile，JediTerm 通过 `TERMINAL_EMULATOR` 大小写无关识别；默认 tail 为 32KB/200 行，JediTerm 为 16KB/120 行。
- [ ] 运行目标测试并检查现有 `sanitize_display_text` 行为未变化。
- [ ] diff 自检并等待提交授权。

### Task 3: 单槽 StreamRenderScheduler

**Files:**
- Create: `tui_components/messages/stream_scheduler.py`
- Test: `tests/tui/test_stream_scheduler.py`

**Interfaces:**
- Produces: `StreamRenderScheduler(flush: Callable[[], Awaitable[None]], interval: float, busy_interval: float, metrics=None)`；异步方法 `mark_dirty()`、`flush_final()`、`close()`；只读属性 `pending`、`dirty`。

- [ ] 写异步失败测试：100 次 `mark_dirty()` 在一个 interval 内只产生一次 flush；flush 期间的新 dirty 在下一帧处理；`flush_final()` 强制输出最新状态；`close()` 后不再调度。
- [ ] 经授权运行测试确认失败。
- [ ] 使用一个 runner task 和一个 dirty flag 实现 latest-wins；不得为每个 chunk 创建独立 task。
- [ ] 增加慢 flush 测试：flush 超过 interval 后下一轮采用 busy interval，但不并发执行两个 flush。
- [ ] 运行测试并检查取消 runner 不吞掉调用方 `CancelledError`。
- [ ] diff 自检并等待提交授权。

### Task 4: 增量 DisplayBuffer

**Files:**
- Create: `tui_components/messages/display_buffer.py`
- Test: `tests/tui/test_display_buffer.py`

**Interfaces:**
- Produces: `IncrementalDisplayBuffer(sanitizer, tail_chars, tail_lines)`；`append(raw_chunk)`；`raw_text()`；`display_text(tail_only=True)`；`version`；`clear()`。

- [ ] 写失败测试：每个 chunk 只调用 sanitizer 一次；多 chunk 结果等于逐 chunk 净化后拼接；tail 同时满足字符和行限制；重复读取同版本复用缓存；raw 内容完整保留。
- [ ] 经授权运行确认失败。
- [ ] 用 list 保存 raw/display chunks，用 version 控制 join 缓存；tail 切片不得修改完整缓存。
- [ ] 加入 CJK、ANSI、emoji、换行边界测试并运行通过。
- [ ] diff 自检并等待提交授权。

### Task 5: 接入正文流式链路

**Files:**
- Modify: `tui_components/messages/stream_handler.py`
- Modify: `tui_components/messages/bot_widget.py`
- Test: `tests/tui/test_stream_interaction.py`

**Interfaces:**
- Consumes: `StreamRenderScheduler`、`IncrementalDisplayBuffer`、terminal profile。
- Produces: `BotMessageWidget.apply_stream_snapshot(display_text: str, raw_text: str | None = None)`；`finalize(final_text: str)`。

- [ ] 写失败测试：高频正文 chunk 只按 scheduler 次数调用 widget snapshot；最终 raw 文本与输入完全一致；取消前强制显示已接收内容。
- [ ] 经授权运行确认失败。
- [ ] `MessageStreamHandler` 在 reset 时创建正文 buffer/scheduler；chunk 只 append+mark_dirty；移除正文路径的周期性完整 sanitize。
- [ ] BotWidget 只渲染传入的已净化 snapshot；finalize 才一次生成完整 Markdown；删除不再使用的 reactive 完整字符串同步路径。
- [ ] 运行目标测试；再做静态检索确保流式路径没有 `sanitize_display_text(self._content_buffer)`。
- [ ] diff 自检并等待提交授权。

### Task 6: thinking 统一调度

**Files:**
- Modify: `tui_components/messages/stream_handler.py`
- Modify: `tui_components/messages/thinking_widget.py`
- Test: `tests/tui/test_stream_interaction.py`

**Interfaces:**
- Produces: `ThinkingWidget.apply_snapshot(char_count: int, display_tail: str | None)`；`is_collapsed`。

- [ ] 写失败测试：thinking-only 1000 chunk 不产生 1000 次 layout/update；折叠时只更新 header；展开时才传 display tail；finalize 恰好更新一次完成状态。
- [ ] 经授权运行确认失败。
- [ ] 移除每 chunk `on_thinking_updated`；正文与 thinking 共用单次 scheduler flush。
- [ ] ThinkingWidget 不自行使用 80ms 时间判断，折叠时不触碰隐藏 content。
- [ ] 运行测试并检索 thinking 流式路径不存在显式 `refresh(layout=True)`。
- [ ] diff 自检并等待提交授权。

### Task 7: MessageList repaint/layout 分离与滚动暂停

**Files:**
- Modify: `tui_components/messages/message_list.py`
- Modify: `qoze_tui.py`
- Test: `tests/tui/test_stream_interaction.py`

**Interfaces:**
- Produces: `MessageList.is_stream_render_paused`；`pause_stream_render()`；`resume_stream_render()`；`apply_stream_snapshot(widget)`；`request_structure_layout()`。

- [ ] 写失败测试：普通 snapshot 不显式请求 layout；连续结构变化合并为一次 layout；向上滚动后 snapshot 不更新正文；回到底部/End 后一次应用最新快照。
- [ ] 经授权运行确认失败。
- [ ] 删除 `_update_widget()` 中矛盾的双 docstring 和 `widget.refresh(layout=True)`；把结构变化集中到单槽 layout 请求。
- [ ] `user_scrolled_up()` 同时暂停流式绘制；`check_scroll_bottom_and_resume()` 和 End 恢复；暂停期间禁止 `scroll_end()`。
- [ ] 运行目标测试，并用 `rg 'refresh\(layout=True\)'` 审核剩余调用只存在于结构变化路径。
- [ ] diff 自检并等待提交授权。

### Task 8: Subagent 与 spinner 降噪

**Files:**
- Modify: `tui_components/messages/subagent_widget.py`
- Modify: `tui_components/messages/message_list.py`
- Modify: `tui_components/messages/tool_status_panel.py`
- Modify: `tui_components/request_indicator.py`
- Test: `tests/tui/test_stream_interaction.py`

**Interfaces:**
- Produces: 共享 250ms ticker；Subagent 折叠时仅 buffer 不刷新正文。

- [ ] 写失败测试：折叠 Subagent stream 不更新隐藏 Static；同一 agent 高频事件遵循 profile interval；6 个工具不创建 6 个独立 Timer；RequestIndicator 间隔不低于 200ms。
- [ ] 经授权运行确认失败。
- [ ] Subagent 使用统一节流并只在展开时更新正文；finalize 仅做一次 Markdown 切换。
- [ ] ToolStatusPanel 用面板级共享 ticker 更新所有 RunningToolItem；RequestIndicator 使用 250ms interval。
- [ ] 运行测试并检查 Timer 在 unmount/stop 后释放。
- [ ] diff 自检并等待提交授权。

### Task 9: P0/P1/P2 综合验证门

**Files:**
- Modify: `docs/superpowers/plans/2026-08-12-tui-stream-performance.md`（仅勾选执行结果）

- [ ] 经用户明确授权后运行 TUI 定向测试集合。
- [ ] 经用户明确授权后运行全量测试（若项目仍无其他测试，则记录仅定向测试）。
- [ ] 经用户授权后执行一个不启动真实模型的模拟 stream benchmark，记录 10,000 chunk、1MB 正文、thinking-only 的 flush 次数与 P95。
- [ ] 用户在 Terminal/iTerm2、IDEA/PyCharm 手工验证 SSE、拖动滚动条、PageUp/End、取消请求。
- [ ] 对照设计指标记录通过项和偏差；不满足时停止，不进入长会话 P3。
- [ ] 展示最终 `git diff --check`、变更摘要和验证证据；是否提交由用户决定。
