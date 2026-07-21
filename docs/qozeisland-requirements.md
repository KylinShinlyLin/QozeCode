# QozeIsland — macOS 状态伴侣需求与技术方案

> 版本: v0.2.1 (菜单栏优先形态)
> 配套技术设计: `qozeisland-tech-design.md`
> 修订记录: v0.1 灵动岛形态 → v0.2 菜单栏优先（§2 形态决策）→
>           v0.2.1 安装改为源码本地构建（§6 M4），文件更名
> 目标: 为终端运行的 QozeCode 提供 macOS 全局实时状态感知与快捷操作入口
> 形态决策: **菜单栏图标 + Popover 为 V1 主形态**；灵动岛（刘海覆盖）降级为 V2 可选皮肤

---

## 1. 背景与问题

QozeCode 是一个长任务型 CLI Agent：用户下达任务后，Agent 会进行几分钟到几十分钟的
"思考 → 调用工具 → 执行命令 → 再思考" 的循环。在此期间用户通常会切走窗口做别的事，
由此产生三个痛点：

1. **状态盲区**: 切走后不知道 Agent 是在跑、卡住了、还是在等我确认。
2. **确认阻塞**: Agent 执行到需要用户确认/批准的节点时，用户不在终端前，任务长时间挂起。
3. **多会话割裂**: QozeCode 可能同时跑在 IDEA 内置终端和 macOS 终端（iTerm2/Terminal.app）
   的多个实例里，用户需要在多个窗口间来回切换寻找"哪个实例在叫我"。

macOS 菜单栏是"全局、轻量、始终可见"的标准状态展示位（参考 1Password / Docker / Stats），
正好解决以上三个痛点。

## 2. 形态决策（v0.2 变更）

### 候选形态对比

| 维度 | 灵动岛（刘海覆盖） | 菜单栏图标 + Popover ✅ |
|------|------------------|------------------------|
| 设备覆盖 | 仅带刘海 MacBook；外接显示器/合盖/老款失效，需降级方案 | **所有 Mac 通用** |
| 技术风险 | 非公开 API（`auxiliaryTopLeftArea` 等），Apple 可能变更 | 完全公开 API（`NSStatusItem` / SwiftUI `MenuBarExtra`），官方标准形态 |
| 被动可见性 | 视野中心，余光可见（唯一杀手锏） | 菜单栏常驻 + 图标动画 + 系统通知补偿，损失可接受 |
| 交互空间 | 展开区域受限，按钮小 | Popover 可达 360×480+，能放完整会话列表、批准大按钮、消息摘要 |
| 开发成本 | 高（窗口层级/刘海几何/降级方案） | 低，`MenuBarExtra` 几十行起骨架 |
| 分发审核 | 非公开 API 有 MAS 审核风险 | 无风险 |

### 结论
**V1 采用菜单栏形态**，灵动岛作为 V2 可选皮肤（仅刘海设备）。
架构上 **UI 渲染层与内核完全解耦**，IPC 协议、状态模型、批准闭环两种形态 100% 复用，
未来加灵动岛皮肤只是新增一个消费同一状态仓库的 SwiftUI View。

```
┌────────────────────────────────────────────────┐
│  内核（形态无关，100% 复用）                       │
│  UDS + NDJSON 协议 / 会话注册表 / 状态模型 / 批准闭环  │
└──────────────────────┬─────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
 菜单栏 Popover UI (V1)        灵动岛 UI (V2 可选皮肤)
 MenuBarExtra                  刘海覆盖 NSPanel（参考 boring.notch）
```

## 3. 产品目标与非目标

### 目标
- **G1 全局状态感知**: 菜单栏图标实时反映所有 QozeCode 会话的聚合状态
  （思考中/执行中/待确认/完成/出错），图标本身即状态灯。
- **G2 快捷批准**: Agent 等待确认时，Popover 置顶显示完整命令 + 批准/拒绝按钮，
  无需切回终端；同时发系统通知做强提醒。
- **G3 会话切换**: Popover 展示多会话列表，点击一键跳转到对应终端窗口
  （IDEA / iTerm2 / Terminal.app）。
- **G4 轻量概览**: Popover 内展示任务摘要、Plan 进度、最近一条 Agent 消息。

### 非目标（本期不做）
- ❌ 完整聊天窗口（菜单栏是"通知+快捷操作"形态，不是 IM）。
- ❌ 移动端/iPhone。
- ❌ 替代 TUI，TUI 仍是主交互界面。
- ❌ 灵动岛皮肤（V2 再议）。

## 4. 用户场景（Use Cases）

| # | 场景 | 用户故事 |
|---|------|---------|
| UC1 | 长任务后台运行 | 用户让 QozeCode 重构代码后切去写文档，菜单栏图标缓慢旋转，知道 Agent 还在干活 |
| UC2 | 批准请求 | 菜单栏图标变橙脉冲 + 收到系统通知 "QozeCode 请求执行 `rm -rf build/`"，点击图标展开 Popover，看清完整命令后点 ✓，全程不切窗口 |
| UC3 | 任务完成 | 图标变绿弹跳一次 + 系统通知 "✓ 任务完成 · 3分42秒"，点击看结果摘要 |
| UC4 | 多实例管理 | IDEA 终端会话（后端）+ iTerm 会话（脚本）同时跑，图标角标显示 "2"，Popover 列表点击跳转对应窗口 |
| UC5 | 错误告警 | Agent 连续工具失败，图标变红常亮 + 通知，用户及时介入 |

## 5. 关键设计决策

### 5.1 终端无关性（核心洞察）

QozeCode 跑在 IDEA 终端还是 macOS 终端，**对菜单栏 App 毫无影响**——
两者之间是 **进程级 IPC**，不依赖任何终端模拟器的能力。
终端只负责显示 TUI；菜单栏 App 直接挂在 QozeCode 的 Python 进程上。

"跳转到会话窗口" 才需要感知终端类型，通过 AppleScript / Accessibility API 实现：
- iTerm2 / Terminal.app: 有成熟 AppleScript 接口，可按 TTY 激活对应窗口/标签。
- IDEA: 通过 `System Events` 激活应用窗口（精确到项目窗口即可）。
- QozeCode 启动时记录自己的 `TTY` + `TERM_PROGRAM` 环境变量
  （iTerm2/Apple_Terminal/vscode/IDEA 均有标识），上报用于窗口定位。

### 5.2 菜单栏 App 实现（V1 主形态）

技术栈: **Swift + SwiftUI（`MenuBarExtra`）+ AppKit 混合**，打包为标准 `.app`，
支持 `LaunchAgent` 开机自启（plist 安装到 `~/Library/LaunchAgents`）。

**图标即状态（菜单栏图标视觉语言）**：

| 状态 | 菜单栏图标 | 辅助提醒 |
|------|-----------|---------|
| 无会话 | 隐藏（`MenuBarExtra` 动态插入/移除） | — |
| idle | Qoze 图标，静态 | — |
| thinking | 图标缓慢旋转/呼吸（SF Symbol 帧动画） | — |
| executing | 图标 + 迷你进度环 | — |
| **waiting_approval** | **图标变橙 + 脉冲闪烁** | **系统通知（横幅+声音，可配置）** |
| done | 变绿 ✓，弹跳一次，数秒后恢复 | 系统通知（可配置） |
| error | 变红 ! 常亮 | 系统通知 |
| 多会话 | 图标旁数字角标（活跃会话数） | — |

**Popover 内容结构**（点击图标展开，约 360×480）：

```
┌──────────────────────────────────┐
│ ⚠️ 待批准 (置顶，仅在有请求时显示)      │
│  QozeCode 请求执行:               │
│  $ rm -rf build/                  │
│  [✓ 批准]        [✗ 拒绝]          │
├──────────────────────────────────┤
│ ● backend-api   k3  ▶ executing  │
│   重构用户模块 · Plan 3/7 · 2:31    │
│   "准备清理构建目录…"        [跳转]   │
│ ● scripts       k3  ⏸ waiting    │
│   批量重命名脚本 · 0:45      [跳转]   │
├──────────────────────────────────┤
│              [设置]    [退出]      │
└──────────────────────────────────┘
```

- 会话条目显示: 项目目录名 + 模型 + 状态 + 耗时 + 最近一条消息 + 跳转按钮。
- 待批准项置顶，高风险命令（regex 命中 `rm|sudo|git push` 等）强制展示完整命令后才可点 ✓。

### 5.3 通信架构（IPC 选型）

```
┌─────────────┐   ┌─────────────┐        ┌──────────────────┐
│ QozeCode #1 │   │ QozeCode #2 │        │   QozeCode.app │
│ (IDEA 终端)  │   │ (iTerm2)    │        │  (Swift/SwiftUI) │
└──────┬──────┘   └──────┬──────┘        └────────▲─────────┘
       │                 │                        │
       └────────┬────────┘                        │
                ▼                                 │
       Unix Domain Socket                         │
       ~/.qoze/island.sock  ◄─────────────────────┘
          (NDJSON 双向流)
```

**选型: Unix Domain Socket + NDJSON（每行一个 JSON 消息）**

| 候选方案 | 结论 | 理由 |
|---------|------|------|
| **UDS + NDJSON** ✅ | 采用 | Python/Swift 均原生支持；零依赖；多客户端天然支持；文件权限 0600 天然鉴权 |
| localhost HTTP/WebSocket | 备选 | 需要端口管理、token 鉴权，更重 |
| macOS DistributedNotification | 否决 | 单向、payload 受限、无法回传操作 |
| XPC | 否决 | 仅适用于同包进程间，跨语言不可用 |

- Socket 路径: `~/.qoze/island.sock`，目录权限 `0700`，socket 权限 `0600`
  （仅当前用户可连，天然免 token）。
- App 作为 **server**，QozeCode 作为 **client** 启动时连接；
  App 未启动时 QozeCode 静默降级（try-connect 失败即关闭集成，不影响主流程）。
- QozeCode 侧封装为 `utils/island_reporter.py`（后台线程 + 队列，发事件绝不阻塞 Agent 主循环）。

### 5.4 消息协议（NDJSON）

所有消息为单行 JSON，含 `type` 字段。

**会话生命周期（client → server）**
```json
{"type":"session.register","session_id":"a1b2","pid":12345,
 "cwd":"/Users/x/proj","tty":"/dev/ttys003","term_program":"iTerm.app",
 "model":"k3","started_at":1753000000}
{"type":"session.unregister","session_id":"a1b2"}
```

**状态上报（client → server）**
```json
{"type":"state","session_id":"a1b2","state":"thinking|executing|waiting_approval|done|error|idle",
 "detail":{"task_summary":"重构用户模块","tool":"execute_command",
           "command":"rm -rf build/","progress":{"done":3,"total":7},
           "last_message":"准备清理构建目录…"}}
```

**批准请求/响应（双向）**
```json
→ {"type":"approval.request","session_id":"a1b2","request_id":"r9",
    "action":"execute_command","summary":"rm -rf build/","risk":"high"}
← {"type":"approval.response","session_id":"a1b2","request_id":"r9","decision":"approve|reject"}
```

**跳转窗口（server 直接执行 AppleScript，无需 client 参与）**
- client 上报的 `tty`/`term_program` 即为此服务。

### 5.5 QozeCode 侧改造点（Hook 注入）

需要植入的事件上报点（均在现有代码中有明确位置）：

1. `qoze_tui.py` / `qoze_code_agent.py` 主循环: LLM 调用开始/结束 → `thinking` / `idle`
2. `tools/execute_command_tool.py` 等工具调用入口: 工具开始/结束 → `executing` + 工具名
3. 用户确认交互点（执行命令前的确认流程）: → `waiting_approval`，
   并在该处**阻塞等待双通道输入**：终端按键 或 App 批准响应（先到先赢）。
   实现上用一个 `threading.Event` + 两个 producer。
4. Plan 模式进度更新点: → `progress`
5. 进程退出（atexit）: → `session.unregister`

所有上报通过 `IslandReporter` 单例，内部队列 + daemon 线程异步发送，
**发送失败/App 不在线时静默丢弃，绝不影响 Agent 主流程**
（可配 `~/.qoze/qoze.conf` 开关 `island.enabled`）。

### 5.6 安全与隐私

- UDS 文件权限 `0600` + 目录 `0700`：仅本机当前用户可通信，无网络暴露面。
- 批准响应校验 `session_id + request_id`，防止串台；`request_id` 一次性消费 + 锁，
  解决"终端确认瞬间 App 也点了批准"的竞态。
- 高风险命令（regex 命中 `rm|sudo|git push` 等）强制 Popover 展示完整命令后才可点 ✓（防误触）。
- 不上报任何代码内容/密钥，仅上报状态元数据；`detail.command` 截断至 200 字符。

## 6. 里程碑与落地计划

| 阶段 | 内容 | 验收标准 | 预估 |
|------|------|---------|------|
| **M1 MVP** | 菜单栏 App 骨架（`MenuBarExtra` + 图标状态动画）；UDS server；QozeCode `IslandReporter`；session.register + state 上报；任务完成/出错系统通知 | 终端跑 QozeCode，图标正确反映 thinking/executing/done/error；kill App 后 Agent 无感知 | 2-3 天 |
| **M2 批准闭环** | approval.request/response 协议；TUI 确认点双通道改造；Popover 待批准置顶 UI + ✓/✗；高风险命令确认 | UC2 全流程通过；终端与 App 同时确认不冲突（request_id 一次性消费） | 2-3 天 |
| **M3 多会话+跳转** | 会话列表 UI + 角标；AppleScript 窗口定位（iTerm2/Terminal/IDEA） | UC3/UC4/UC5 通过 | 2-3 天 |
| **M4 打磨** | LaunchAgent 自启（可选）；设置面板（通知开关、动画开关）；`build_island.sh` / `uninstall_island.sh` 构建卸载脚本与 install.sh 集成（`--with-island`，默认不装） | 源码一条命令构建安装 | 2 天 |
| **V2（可选）** | 灵动岛皮肤：刘海覆盖 NSPanel + 无刘海降级悬浮胶囊，消费同一状态仓库 | 刘海设备上双形态可切换 | 另行评估 |

总计 V1 约 1.5-2 周（1 人）。

## 7. 风险与开放问题

1. **IDEA 终端窗口精确定位**：AppleScript 对 JetBrains 系支持有限，最坏情况只能激活
   IDEA 应用本身（可接受降级）。开放问题：是否接受用 Accessibility API 做更激进的定位？
2. **双通道批准的状态一致性**：用 `request_id` 一次性消费 + 锁保证，M2 需专项测试。
3. **图标动画在 macOS 菜单栏的帧率限制**：菜单栏图标更新频率过高会被系统节流，
   呼吸/旋转动画需控制在合理帧率（~5fps 离散帧），M1 验证。
4. **是否开放给第三方终端 Agent**？协议设计已通用化，未来可演进为
   "Agent 状态伴侣平台"，本期不做。
