# QozeCode TUI 与 macOS 通知栏性能优化设计

> 日期：2026-08-12  
> 状态：待用户复核

## 1. 背景与目标

当前问题包括：Agent 执行时 macOS 菜单栏 Popover 打开和 Tab 切换卡顿；IDEA/PyCharm JediTerm 中 SSE 输出时 TUI 卡顿甚至无法滚动；当前进程内消息增加后滚动持续退化。

本设计采用平衡型、分阶段重构：先恢复交互可用性，再消除长输出的二次处理成本，最后限制长会话 UI 树规模。

核心目标：

- SSE 连续可感知，但允许合并或跳过中间帧；
- UI 更新采用 latest-wins，禁止刷新任务排队；
- 滚动、点击、Tab 切换优先于动画和中间流式帧；
- UI 历史窗口与 LangGraph 上下文解耦，不裁剪 Agent 上下文；
- Terminal/iTerm2 与 JediTerm 使用不同刷新预算；
- 所有性能降级不得影响 Agent 主流程和最终内容完整性。

非目标：不更换 Textual/LangGraph/SwiftUI；不实现 Island 审批闭环；不修改模型上下文压缩策略；第一阶段不实现通用任意高度虚拟列表。

## 2. 根因摘要

### 2.1 TUI

1. `MessageList._update_widget()` 的注释称不强制布局，实际仍调用 `refresh(layout=True)`；
2. thinking 内部虽节流，外层每个 thinking chunk 仍可能触发布局；
3. `sanitize_display_text()` 周期性扫描完整累计文本，长回复累计成本趋向二次增长；
4. 正文、thinking、累计 AI message 存在多份不可变字符串持续 `+=`；
5. 完成回复长期保留完整 Markdown Widget 子树，`ScrollableContainer` 不虚拟化；
6. 多个 100ms spinner Timer 与 SSE 争用事件循环；
7. JediTerm 的全屏 diff 和 Unicode 渲染吞吐较低，放大上述问题。

### 2.2 macOS 通知栏

1. thinking/waiting/executing 使用无限连续 SwiftUI 动画；
2. `PopoverView` 每秒在 MainActor 强制整页 body 重算，但当前没有必须逐秒更新的数据；
3. `TokenUsageStore.reloadFromDisk()` 在 MainActor 同步读文件、解码 JSON；
4. 菜单栏图标和通知附件缺少缓存；
5. sessions/days 更新缺少相同值去重。

## 3. 总体原则

```text
SSE chunk / Island NDJSON
        ↓
状态累积（原始内容、展示内容、最新状态）
        ↓
刷新调度（单槽 latest-wins、帧率预算、交互暂停）
        ↓
展示（流式尾部窗口、最终 Markdown、静态状态图标）
```

- 数据接收不等待每个 UI 帧；
- 每个组件最多一个 pending flush；
- 新快照覆盖旧待刷新快照；
- UI 忙时丢中间帧，不丢最终内容；
- 普通 repaint 与结构性 layout 分离；
- 用户主动交互时暂停非必要动态更新。

## 4. TUI 设计

### 4.1 统一 StreamRenderScheduler

新增轻量调度器：chunk 到达只标记 dirty；同一时刻最多一个 flush；到帧间隔后读取最新 buffer；flush 超预算时自适应降频；完成、取消、异常必须强制最终 flush，并保持现有取消语义。

初始预算：

| 环境 | 正常上限 | UI 忙时下限 |
|---|---:|---:|
| Terminal/iTerm2 | 15–20 FPS | 10 FPS |
| JediTerm | 8–12 FPS | 6 FPS |

这里是最大有效刷新频率，没有新数据时不运行 Timer。

### 4.2 thinking 与正文统一调度

- thinking 不再通过每 chunk 回调触发布局；
- 默认折叠时只更新短 header，不更新隐藏正文；
- 展开后低频渲染可见尾部；
- finalize 只更新一次完成状态。

### 4.3 增量净化与 Buffer 所有权

- `raw_chunks` 保存原始内容；
- `display_chunks` 保存每个新增 chunk 一次净化后的内容；
- 禁止每帧对完整累计文本重跑正则；
- 仅在最终内容或确实需要时 join，并按内容版本缓存；
- 减少 BotWidget、StreamHandler、AI message 对同一正文的重复完整拷贝。

### 4.4 流式尾部窗口

流式阶段只展示最近 120–200 行或 16–32KB；超出部分仍保存在 raw buffer。结束后执行一次最终 Markdown 更新。特别长的最终正文允许折叠或分段，避免单个 Markdown 创建巨大子树。

### 4.5 用户滚动优先

向上滚动后立即关闭自动跟随；继续接收数据但暂停正文布局；不调用 `scroll_end()`；只允许低频短状态提示。滚回底部或按 End 后一次同步最新尾部并恢复跟随。

### 4.6 布局与 Timer

- 流式普通路径删除显式 `refresh(layout=True)`；
- mount/unmount、折叠切换、Static/Markdown 切换等结构变化才请求布局；
- 同一帧合并结构布局；
- RequestIndicator、ToolStatus、Subagent spinner 调整到 200–250ms；
- 多工具改用共享 Timer；
- Sidebar 在任务执行期间降低更新频率或无变化时跳过。

### 4.7 长会话 UI 窗口

- 默认保留最近 20–30 个对话轮次的完整 Widget；
- 更早内容从 DOM 卸载为轻量历史段；
- 顶部提供“加载更早消息”分页入口；
- 工具结果可只保留摘要；
- 不删除 LangGraph/checkpointer 消息，不影响模型上下文。

第一版采用稳定的分段窗口，不实现复杂通用虚拟列表。

## 5. macOS 通知栏设计

### 5.1 动画与图标

第一阶段直接取消无限旋转/呼吸，使用静态 symbol 和状态色。若后续恢复动效，只允许 3–4 FPS 离散帧，Popover 打开时停止。按 state/size 缓存菜单栏 `NSImage`、徽章和通知附件 PNG，SwiftUI body 不重复离屏绘图。

### 5.2 Popover 事件驱动

删除 1 秒强制 Timer，只依赖状态发布刷新。手动刷新按钮执行真实 reload，而非修改无意义 tick。未来若显示耗时，只刷新单个耗时 Label。

### 5.3 TokenUsage 异步加载

文件读取、JSON 解码和字典转换在后台 Task；最终赋值回 MainActor。使用 mtime/size 或版本避免重复解析；Tab 首帧不得等待磁盘；通过 generation/version 防止旧磁盘结果覆盖更新的 IPC 快照。

### 5.4 状态去重

相同 state/detail 不重新发布 sessions；相同用量快照不发布 days；相同终态不重复创建回落任务。Socket 解码继续在后台，MainActor 只应用轻量状态。

## 6. 性能埋点与验收

### 6.1 埋点

`QOZE_PERF_DEBUG=1` 时按 2–5 秒聚合记录，不逐 chunk 同步写文件：chunk/s、flush/s、合并帧、flush P50/P95/max、sanitize 耗时、layout 次数、Widget 数、展示/原始字符数、事件循环延迟。

macOS 使用开发期开关和 signpost 记录 Popover 首帧、Tab 首帧、TokenUsage read/decode/apply、SessionStore apply、图标生成及 MainActor 长任务。

### 6.2 验收目标

| 场景 | 目标 |
|---|---|
| 执行期间点击菜单栏到 Popover 首帧 | P95 < 100ms |
| 会话/用量 Tab 切换 | P95 < 80ms |
| Terminal/iTerm2 SSE | 15–20 FPS，队列不积压 |
| JediTerm SSE | 8–12 FPS，队列不积压 |
| SSE 期间滚动响应 | < 100ms |
| 单次 TUI flush | 原生 P95 < 16ms；JediTerm P95 < 35ms |
| 100 轮会话滚动退化 | 不超过初始成本约 2 倍 |
| 内容一致性 | 不丢、不重、取消时保留已接收内容 |

## 7. 分阶段交付

### P0：基线与测试夹具

增加默认关闭的聚合埋点；建立高频 chunk、长回复、thinking、工具、滚动暂停测试夹具；记录 Terminal/iTerm2/JediTerm 和 Island 基线。

### P1：恢复交互可用性

删除 Island 无限动画和 Popover Timer；TokenUsage 异步读取；thinking/正文统一节流；合并 TUI flush；停止每 chunk layout；滚动时暂停重绘；降低 spinner 频率。

### P2：消除长回复二次成本

增量 sanitize；chunk list 和 join 缓存；流式尾部窗口；最终 Markdown 单次切换；图标与通知附件缓存。

### P3：控制长会话规模

最近轮次窗口；旧消息轻量归档和分页；工具摘要；100 轮及超长 Markdown 压力验证。

每阶段独立验证。若指标不改善，不叠加下一阶段，先回到根因分析。

## 8. 测试策略

单元测试覆盖：调度器 latest-wins、最多一个 pending flush、最终强制 flush、增量净化一致性、滚动暂停/恢复、状态去重、异步磁盘竞态。

性能场景覆盖：10,000 小 chunk、1MB 正文、thinking-only、多工具/多 Subagent、20/50/100 轮、表格/代码块/CJK、JediTerm emoji 和控制字符。

人工验证覆盖：Terminal.app、iTerm2、IDEA/PyCharm；SSE 时滚动/选择/End；执行时反复打开 Island 和切 Tab；多会话并发；用量文件缺失、损坏、较大。

## 9. 风险与回滚

| 风险 | 控制 |
|---|---|
| 移除 layout 后高度不更新 | 先用夹具确认 Textual 行为；结构变化保留合并 layout |
| 合帧导致最终内容缺失 | finalize/cancel/error 强制最终 flush |
| 滚动后不能恢复跟随 | 底部阈值与 End 键双通道恢复 |
| UI 卸载影响上下文 | UI 与 LangGraph state 分离，不删 checkpoint |
| 异步用量读取竞态 | generation/version 校验后应用 |
| 静态图标状态感变弱 | 保留明确颜色和 symbol，后续只恢复低频动效 |
| Textual 版本差异 | 记录并固定验证版本，避免依赖未声明内部行为 |

## 10. 预期改动边界

主要文件：

- `tui_components/messages/{stream_handler,message_list,bot_widget,thinking_widget,subagent_widget,tool_status_panel}.py`
- `tui_components/request_indicator.py`
- `tui_components/terminal_compat.py`
- `qoze_tui.py`
- `macos/QozeCode/Sources/QozeCodeApp.swift`
- `macos/QozeCode/Sources/UI/{PopoverView,MenuBarIcon,StateIconRenderer}.swift`
- `macos/QozeCode/Sources/{TokenUsageStore,SessionStore}.swift`

P1 不顺带重构 Agent 业务、MCP、音频或审批协议。
