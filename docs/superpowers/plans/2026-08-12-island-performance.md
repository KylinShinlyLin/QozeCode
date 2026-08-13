# macOS Island Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 Agent 执行期间菜单栏动画和 MainActor I/O 对点击、Popover 首帧及 Tab 切换的阻塞。

**Architecture:** 菜单栏改为事件驱动静态状态渲染；图像按状态缓存；TokenUsage 的 I/O/解码移到后台并使用 generation 防竞态；SessionStore 对相同状态更新去重。

**Tech Stack:** Swift、SwiftUI、AppKit、UserNotifications、Unix Domain Socket

## Global Constraints

- 第一阶段取消无限连续动画，状态仍通过 symbol 和颜色表达。
- Popover 不使用整页周期强刷。
- 磁盘读取和 JSON 解码不得阻塞 MainActor。
- IPC 断线、文件不存在或损坏继续静默降级。
- 不修改 IPC 消息格式和审批协议。
- 未经用户确认不得构建、安装、启动 App 或运行测试；不得自动提交 Git。

---

## File Map

- Modify `macos/QozeCode/Sources/QozeCodeApp.swift`: 静态状态标签、移除无限动画。
- Modify `macos/QozeCode/Sources/UI/MenuBarIcon.swift`: NSImage 状态缓存。
- Modify `macos/QozeCode/Sources/UI/StateIconRenderer.swift`: 徽章和通知附件缓存。
- Modify `macos/QozeCode/Sources/UI/PopoverView.swift`: 移除 Timer，真实手动刷新。
- Modify `macos/QozeCode/Sources/TokenUsageStore.swift`: 后台 reload、mtime/generation、防覆盖。
- Modify `macos/QozeCode/Sources/UI/TokenUsageView.swift`: 非阻塞触发 reload。
- Modify `macos/QozeCode/Sources/SessionStore.swift`: Equatable 快照和无效更新去重。
- Modify `macos/QozeCode/Sources/Services/NotificationService.swift`: 使用缓存附件。
- Create `macos/QozeCode/Sources/PerformanceSignposts.swift`: 开发期开关 signpost。

### Task 1: Island 性能 signpost

**Files:**
- Create: `macos/QozeCode/Sources/PerformanceSignposts.swift`
- Modify: `macos/QozeCode/Sources/Server/IslandServer.swift`
- Modify: `macos/QozeCode/Sources/SessionStore.swift`

**Interfaces:**
- Produces: `IslandPerf.begin(_:)`、`end(_:_:)`、`event(_:detail:)`；默认低开销且不写同步文件。

- [ ] 实现基于 `OSLog`/`OSSignposter` 的封装，覆盖 message decode、store apply、token reload 和图标生成。
- [ ] 开关关闭时不拼接大 detail，不调用 `DebugLog` 高频写文件。
- [ ] 静态检查所有 begin/end 成对，异常/guard 路径也结束区间。
- [ ] 经用户授权后再构建验证；构建前先展示命令和对用户目录的影响。
- [ ] diff 自检并等待提交授权。

### Task 2: 移除连续菜单栏动画

**Files:**
- Modify: `macos/QozeCode/Sources/QozeCodeApp.swift`

- [ ] 删除 `executingSpin`、`phaseAnimator`、`repeatForever` 和 `onAppear` 动画启动。
- [ ] 所有非 idle 状态只渲染静态缓存图像；idle 保持 template SF Symbol；多会话角标保持。
- [ ] 静态检索确认菜单栏 label 不再存在无限动画 API。
- [ ] 经授权构建并人工确认七种状态图标仍可辨识。
- [ ] diff 自检并等待提交授权。

### Task 3: 菜栏与通知图标缓存

**Files:**
- Modify: `macos/QozeCode/Sources/UI/MenuBarIcon.swift`
- Modify: `macos/QozeCode/Sources/UI/StateIconRenderer.swift`
- Modify: `macos/QozeCode/Sources/Services/NotificationService.swift`

**Interfaces:**
- Produces: `MenuBarIcon.tintedImage(for:pointSize:)` 维持原签名但内部缓存；`StateIconRenderer.icon(for:size:)` 缓存；`notificationIconURL(for:)` 同状态复用 URL。

- [ ] 用 `state.rawValue + normalized size` 构建稳定缓存键，缓存访问限定 MainActor 或使用锁保护。
- [ ] 通知 PNG 首次生成后复用；文件被系统清理时允许重建。
- [ ] signpost 记录 cache hit/miss，不记录每帧日志。
- [ ] 经授权构建并人工检查深/浅色菜单栏图标。
- [ ] diff 自检并等待提交授权。

### Task 4: Popover 改为事件驱动

**Files:**
- Modify: `macos/QozeCode/Sources/UI/PopoverView.swift`

- [ ] 删除 `tick`、`refreshTimer`、`let _ = tick` 和 `onReceive`。
- [ ] 手动刷新按钮改为异步调用 `TokenUsageStore.shared.reloadFromDisk()`，会话列表继续依赖 `SessionStore.@Published`。
- [ ] 确保切换 Tab 不重新创建周期 Timer。
- [ ] 经授权构建并人工连续打开/关闭 Popover、切换 Tab 50 次。
- [ ] diff 自检并等待提交授权。

### Task 5: TokenUsage 后台读取与竞态保护

**Files:**
- Modify: `macos/QozeCode/Sources/TokenUsageStore.swift`
- Modify: `macos/QozeCode/Sources/UI/TokenUsageView.swift`

**Interfaces:**
- Produces: `func reloadFromDisk() async`；内部 `reloadGeneration: UInt64`、`lastFileSignature`、`lastAppliedSourceVersion`。

- [ ] 把文件 Data 读取、JSON decode 和 convert 放入 `Task.detached(priority: .utility)`；MainActor 只发起任务和应用结果。
- [ ] 文件不存在/损坏返回无更新，不清空已有 IPC 数据。
- [ ] 以 mtime+size 作为快速 signature，相同文件跳过 decode。
- [ ] 每次 IPC apply 增加 source generation；磁盘任务返回时只在 generation 未落后时应用，防止旧文件覆盖新 IPC。
- [ ] `TokenUsageView.onAppear` 使用 `Task { await store.reloadFromDisk() }`，首帧不等待。
- [ ] 经授权构建；人工验证缺失、损坏和较大 JSON 文件时 Tab 仍立即切换。
- [ ] diff 自检并等待提交授权。

### Task 6: SessionStore 更新去重

**Files:**
- Modify: `macos/QozeCode/Sources/SessionStore.swift`

**Interfaces:**
- Produces: `Session: Equatable`；`applyDetail` 返回 `Bool changed`；transition 在 state/detail 都未变化时直接返回。

- [ ] 为 `progress` 使用可比较的独立 `PlanProgressValue`，避免 tuple 阻碍自动 Equatable。
- [ ] register 相同快照不重复发布；state/detail 相同不重写字典；token usage 交给其 store 自行去重。
- [ ] 仅真实状态变化触发通知；相同终态不取消并重建 5 秒回落任务。
- [ ] 保持断线 remove 和聚合优先级语义不变。
- [ ] 经授权构建并用多工具/多会话人工验证状态更新。
- [ ] diff 自检并等待提交授权。

### Task 7: Island 综合验证门

- [ ] 经授权运行 `bash macos/build_island.sh` 前明确说明会覆盖 `~/Applications/QozeCode.app` 并签名；未授权则只做静态检查。
- [ ] 经授权启动 App 后使用 Instruments/Time Profiler 或 signpost 记录 idle、thinking、executing 下 MainActor 活动。
- [ ] 执行任务期间测量菜单点击到首帧、会话/用量 Tab 切换，目标分别 P95 <100ms、<80ms。
- [ ] 验证通知、done→idle 回落、多会话角标、断线清理没有回归。
- [ ] 展示 `git diff --check`、验证证据和未解决偏差；是否提交由用户决定。
