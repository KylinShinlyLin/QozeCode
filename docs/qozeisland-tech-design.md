# QozeIsland 技术设计文档

> 版本: v0.3
> 对应需求文档: `qozeisland-requirements.md`（菜单栏优先形态）
> 修订记录: v0.1 初版选型论证 → v0.2 构建分发改为源码本地构建（§2.8），
>           通知中断级别降级（§2.6），目录结构修正（§7）
> 范围: 技术选型论证、模块设计、接口定义、关键实现方案

---

## 1. 总体架构

```
┌────────────────────────────────────────────────────────────┐
│ QozeCode.app (macOS 菜单栏应用, Swift 6 + SwiftUI)           │
│                                                            │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ MenuBarUI   │  │ PopoverUI    │  │ NotificationSvc   │  │
│  │ (图标状态动画) │  │ (会话列表/批准)│  │ (UNUserNotification)│ │
│  └──────┬──────┘  └──────┬───────┘  └─────────┬─────────┘  │
│         └────────────────┼────────────────────┘            │
│                          ▼                                 │
│              ┌───────────────────────┐                     │
│              │  SessionStore          │  @Observable, 单一数据源 │
│              │  (会话注册表/状态机/批准队列)│                     │
│              └───────────┬───────────┘                     │
│                          ▼                                 │
│              ┌───────────────────────┐   ┌──────────────┐  │
│              │  IslandServer          │   │ FocusService │  │
│              │  (UDS server, NDJSON)  │   │ (AppleScript)│  │
│              └───────────┬───────────┘   └──────────────┘  │
└──────────────────────────┼─────────────────────────────────┘
                           │ ~/.qoze/island.sock (0600)
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ QozeCode #1    │  │ QozeCode #2    │  │ QozeCode #N    │
│ IslandReporter │  │ IslandReporter │  │ IslandReporter │
│ (queue+thread) │  │ (queue+thread) │  │ (queue+thread) │
└───────────────┘  └───────────────┘  └───────────────┘
```

**进程拓扑**: 1 个 server（App）对 N 个 client（QozeCode 实例），
client 仅上报事件与接收批准响应，client 之间无感知。

---

## 2. 技术选型论证

### 2.1 UI 框架: SwiftUI `MenuBarExtra` vs AppKit `NSStatusItem`

| 维度 | SwiftUI `MenuBarExtra` ✅ | AppKit `NSStatusItem` + `NSPopover` |
|------|--------------------------|-------------------------------------|
| 代码量 | 声明式，骨架 ~50 行 | 模板代码多（delegate、popover 控制、约束） |
| 动态显隐 | `isInserted` 绑定状态，一行控制 | 需手动管理 `statusItem` 生命周期 |
| 图标动画 | ⚠️ 弱项：`MenuBarExtra` 的 label 是 SwiftUI View，但菜单栏区域刷新有系统节流，复杂动画不可靠 | ✅ 强项：直接持有 `NSStatusItem.button`，可对 `NSImage` 做帧替换，动画完全可控 |
| Popover 内容 | `.menuBarExtraStyle(.window)` 直接放任意 SwiftUI 视图树 | 需手动桥接 `NSHostingController` |
| 系统兼容 | macOS 13+ | 全版本 |

**决策: 混合方案——主体用 SwiftUI `MenuBarExtra`（window 样式），
图标动画通过 AppKit 桥接实现。**

理由：
1. Popover 内容（会话列表、批准面板）是标准 UI，SwiftUI 开发效率碾压，无争议。
2. 唯一短板是图标动画。解法：`MenuBarExtra` 创建后，通过
   `NSApp.windows` / 私有桥接拿到 `NSStatusItem.button`，
   用 `Timer`（5fps 离散帧）替换 `button.image` 实现呼吸/旋转帧动画。
   备选：直接用预生成的 SF Symbol 变体帧（`arrow.triangle.2.circlepath` 等符号
   配合 `NSImage(symbolName:)` + rotation effect 离线渲染），避免私有 API。
3. macOS 13+ 的 `MenuBarExtra` 已覆盖目标用户（2026 年 macOS 13 以下份额可忽略）。

**风险预案**: 若桥接取 button 不稳定，降级为「静态图标 + 颜色区分」+
系统通知补偿，体验损失可接受（M1 验证点）。

### 2.2 IPC: Unix Domain Socket + NDJSON

已在需求文档对比过（UDS vs HTTP/WebSocket vs DistributedNotification vs XPC），
此处展开 **Swift 侧 socket 实现**的二次选型：

| 维度 | Network.framework (`NWListener`) ✅ | POSIX socket API | SwiftNIO |
|------|------------------------------------|--------------------|----------|
| UDS 支持 | ✅ `NWParameters(requiredInterfaceType: .loopback)` 不支持 UDS，但 `NWListener` 可用 `NWEndpoint.unix(path:)` 自定义 endpoint（macOS 11+ 通过 `NWParameters()` + `NWProtocolFramer`） | ✅ 原生 | ✅ 原生 |
| 行协议解析 | 需配合 `NWProtocolFramerImplementation` 自定义 message framer | 手动 buffer 切分 | `LineBasedFrameDecoder` 开箱即用 |
| 依赖 | 系统框架，零依赖 | 系统 API | 需引入 SwiftNIO 包（重） |
| 并发模型 | `NWConnection` 回调/DispatchQueue，天然支持多连接 | 手动线程/kqueue | EventLoop |

**决策: Network.framework + 自定义 `NWProtocolFramer`（按 `\n` 分帧）。**

理由：
1. 零第三方依赖，App 体积和供应链风险最小。
2. `NWListener(service:nil, using:)` + `NWEndpoint.unix` 原生支持 UDS，
   多 client 连接由框架管理（每个 client 一个 `NWConnection`）。
3. SwiftNIO 对本场景（N ≤ 5 个连接、消息频率 < 10/s）严重过剩。
4. POSIX API 可行但需手写 buffer 管理和错误处理，NW 框架已封装断连检测
   （`stateUpdateHandler` → client 掉线自动清理会话，这对「QozeCode 进程被杀」
   场景至关重要——**依靠 socket 断开作为 session.unregister 的兜底**）。

**NDJSON 而非 length-prefix**: 调试友好（`nc -U ~/.qoze/island.sock` 可直接
人工收发）、Python `json` + Swift `Codable` 零成本；单消息 < 4KB，
无粘包性能顾虑，framer 实现仅 ~30 行。

### 2.3 序列化: JSON (`Codable`) vs Protobuf/MessagePack

**决策: JSON。**
消息量 < 10 msg/s，payload < 4KB，序列化性能完全不是瓶颈；
JSON 的可读性、双端零依赖（Python `json` / Swift `Codable`）、
协议演进时字段增删的向后兼容性（忽略未知字段）都优于二进制方案。
协议预留 `version` 字段应对未来破坏性变更。

### 2.4 QozeCode 侧: `IslandReporter` 实现选型

| 维度 | 后台线程 + queue ✅ | asyncio | 同步直发 |
|------|--------------------|---------|---------|
| 与现有代码契合 | QozeCode 主流程是同步 + 局部 asyncio（TUI），threading 无侵入 | 需在同步代码里桥接事件循环，复杂 | — |
| 阻塞风险 | 队列缓冲，发送线程独立，主流程零阻塞 | 同左 | ❌ socket 异常时阻塞 Agent 主循环，不可接受 |
| 复杂度 | `queue.Queue` + daemon thread，~80 行 | 中 | 低 |

**决策: `threading` + `queue.Queue` + daemon 线程。**

关键设计：
```python
class IslandReporter:
    - __init__: 尝试连接 ~/.qoze/island.sock（timeout=0.5s），
      失败则 self.enabled=False，后续所有 report* 调用立即 return（静默降级）
    - 内部 Queue(maxsize=256)：满时丢弃最旧消息（状态类消息允许丢失，
      最新的 state 会覆盖；approval.request 不允许丢弃 → 入队失败时
      直接走终端确认通道，视为无 App 接入）
    - daemon 发送线程：批量 drain 队列 → 逐行写入 socket；
      写失败置 enabled=False 并关闭连接（App 被杀场景）
    - 重连策略（v0.3.1 实现期提前到 M1）：App 后启动/运行中重启时，后台线程每 5s
      静默重试连接；重连成功立即补发 session.register + 缓存的最新 state，
      Island 上直接呈现当前真实状态而非错误的 idle
    - atexit 注册 session.unregister + socket close
```

### 2.5 状态管理: Swift 侧 `SessionStore`

**决策: 单例 `SessionStore: ObservableObject`（Swift 6 用 `@Observable`），
作为 App 内唯一数据源。**

- 持有 `[String: Session]` 字典（session_id → Session 值类型）。
- `IslandServer` 在后台队列解析消息 → 封装为 `Event` 枚举 →
  `DispatchQueue.main` 派发给 `SessionStore.apply(event)`。
- UI 层（MenuBar label / Popover）纯声明式订阅，无回调地狱。
- **聚合状态计算属性**（菜单栏图标显示什么）：
  `error > waiting_approval > executing > thinking > done(短暂) > idle`，
  多会话取最高优先级状态 + 活跃会话数。
- 并发安全：所有变更收敛到 main actor，避免数据竞争（Swift 6 strict concurrency 友好）。

### 2.6 系统通知: `UNUserNotificationCenter`

**决策: `UNUserNotificationCenter`（现代 API），不用废弃的 `NSUserNotification`。**

- 触发点收敛在 `SessionStore`：状态迁移到 `waiting_approval` / `done` / `error` 时发通知
  （各自可在设置中独立开关）。
- 通知 `categoryIdentifier` 携带 `session_id`，点击通知 → 打开 Popover 并定位到对应会话。
- 权限：首次启动请求 `alert + sound` 授权；被拒绝则静默降级为纯图标提醒。
- 打断策略：V1 统一使用普通中断级别（`.timeSensitive` 需要完整签名 entitlement，
  ad-hoc 本地构建下不可用）；专注模式下的提醒强度在 M2 实测验证（见 §6 开放问题 #2）。

### 2.7 窗口跳转: AppleScript vs Accessibility API

| 终端 | 方案 | 可行性 |
|------|------|--------|
| iTerm2 | AppleScript: `tell application "iTerm2"` → 遍历 window/tab/session，匹配 `tty` 精确激活 | ✅ 精确到 tab |
| Terminal.app | AppleScript: 遍历 window 的 tab，`tty` 属性匹配，设置 `selected` | ✅ 精确到 tab |
| VS Code 终端 | 无 tty 级 API；`open -a "Visual Studio Code"` 激活应用 | ⚠️ 应用级 |
| IDEA 系 | 无终端 API；AppleScript `tell application "System Events"` 激活进程窗口 | ⚠️ 应用级 |

**决策: 双层策略——tty 匹配优先（iTerm2/Terminal），失败降级为 `open -a` 应用级激活。**

- `FocusService` 按 `term_program` 分发到对应 handler，AppleScript 用
  `NSAppleScript` 或 `osascript` 子进程执行（选 `NSAppleScript`，错误信息更丰富）。
- AppleScript 源码以资源文件内嵌，避免硬编码字符串散落。
- Accessibility API（AXUIElement）能精确到 IDEA 窗口但需用户授权辅助功能权限，
  授权弹窗体验差 → 不采用。
- 最终实现（v0.4）：QozeCode register 时沿进程树探测最近 GUI 祖先
  （`.app/Contents/MacOS` 判定）上报 `host_app_pid/name`；
  IDEA 系走 `NSRunningApplication(processIdentifier:).activate` 应用级激活，
  **无需 AppleScript 自动化权限**；iTerm2/Terminal 走 AppleScript tty 精确匹配，
  失败自动降级到 pid 激活。

### 2.8 构建与分发（v0.2 修订: 源码本地构建，无签名无公证）

**决策: 源码随 QozeCode 仓库分发（`macos/QozeCode/`），用户本地 `xcodebuild` 构建，
ad-hoc 签名（`CODE_SIGN_IDENTITY="-"`），安装为可选步骤。**

理由：
1. 本地构建产物无 quarantine xattr，Gatekeeper 不拦截，**无需开发者 ID 签名与公证**。
2. 目标用户即开发者，机器普遍已有 Xcode CLT；构建脚本检测缺失时提示 `xcode-select --install` 后退出。
3. 非沙盒运行，AppleScript 控制 iTerm2/Terminal 无 entitlement 障碍。
4. 取消原「开发者签名 + notarize + DMG」方案（封闭分发场景才需要，本期无此需求）。

**安装流程（三级可选控制）**：

| 级别 | 机制 | 说明 |
|------|------|------|
| 安装时 | `install.sh` 询问 / `--with-island` 参数；或独立执行 `bash macos/build_island.sh` | 默认不安装 |
| 运行时 | `~/.qoze/qoze.conf` `[island] enabled` 开关 | 装了也可临时禁用 |
| 天然降级 | App 不存在 → connect 失败 → QozeCode 零感知 | 架构自带 |

**构建脚本**（v0.3 实现期修正，`macos/build_island.sh`）：
放弃 xcodebuild/xcodeproj（手写 pbxproj 维护成本高），改为 `swiftc` 直接编译 +
手工组 bundle，前置依赖从完整 Xcode 降为 **Command Line Tools** 即可：
```bash
swiftc -O -parse-as-library -target $(uname -m)-apple-macosx13.0 \
       -framework SwiftUI -framework Foundation -framework UserNotifications \
       -module-name QozeCode $(find Sources -name "*.swift") -o QozeCode
# 组装 .app bundle (Info.plist: LSUIElement=true) + codesign --sign - (ad-hoc)
```

**启动模式**：手动启动（默认）/ LaunchAgent 开机自启（安装时询问是否写入
`~/Library/LaunchAgents/com.qoze.code.plist`）/ QozeCode 拉起
（`[island] auto_launch=true` 时 `open -a QozeCode`）。

**卸载**（`macos/uninstall_island.sh`）：移除 LaunchAgent plist +
`~/Applications/QozeCode.app`，socket 文件由 App 退出时自行清理。

### 2.9 语言/运行时版本

| 组件 | 选型 | 约束 |
|------|------|------|
| App | Swift 6 + SwiftUI, macOS 14+ (deployment target, `@Observable` 宏门槛) | `MenuBarExtra` 需 13+；Swift 6 strict concurrency 提前规避数据竞争 |
| QozeCode 侧 | Python 3.9+（与项目现有 pyproject 一致） | 仅用标准库（socket/threading/queue/json），零新依赖 |
| 协议 | NDJSON over UDS，预留 `version: 1` 字段 | 破坏性变更升 version，App 对未知 version 提示升级 |

---

## 3. 协议详细设计

### 3.1 消息总表

| 方向 | type | 说明 | 丢失容忍 |
|------|------|------|---------|
| C→S | `session.register` | 连接后第一条消息，携带会话元数据 | ❌（连接建立即发送） |
| C→S | `session.unregister` | 正常退出时发送 | ✅（socket 断开兜底） |
| C→S | `state` | 状态迁移 + detail（增量覆盖式） | ✅（最新值覆盖） |
| C→S | `approval.request` | 请求批准，阻塞等待响应 | ❌（不得丢弃） |
| S→C | `approval.response` | 批准/拒绝 | ❌ |
| C→S | `ping` | 5s 空闲心跳，探测死连接（idle 会话不写消息，只能靠心跳发现 Island 已退出）；App 侧按未知类型忽略 | ✅ |

### 3.2 状态机（单会话）

```
            ┌──────┐
            │ idle │◄────────────────────┐
            └──┬───┘                     │
   LLM 调用开始 │                          │ 所有终态后回到 idle
               ▼                          │
          ┌──────────┐  工具调用开始  ┌───────────┐
          │ thinking │──────────────►│ executing │
          └────┬─────┘               └─────┬─────┘
               │  需用户确认                 │ 工具结束
               ▼                           │
       ┌──────────────────┐               │
       │ waiting_approval │───────────────┘
       └────────┬─────────┘  批准/拒绝(双通道)
                │
     ┌──────────┼───────────┐
     ▼          ▼           ▼
  ┌──────┐  ┌───────┐  ┌───────┐
  │ done │  │ error │  │(继续)  │
  └──────┘  └───────┘  └───────┘
```

- `done`/`error` 为瞬时态：App 侧展示 3-5 秒后自动回落 `idle`（由 SessionStore 计时器控制）。
- 非法迁移（如 idle → done）App 侧宽容处理（直接应用并记 debug 日志），不拒绝。

### 3.3 关键竞态处理

**批准双通道竞态**（终端确认 与 App 点击 同时发生）：
- QozeCode 侧：`ApprovalBroker` 持有 `request_id → threading.Event`；
  终端线程与 socket 接收线程任一先 set 即生效，后者发现 Event 已 set 则丢弃。
- App 侧：`approval.response` 发出后将该 request 标记为 pending；
  收到下一个 `state` 消息（离开 waiting_approval）即清除待批准 UI；
  超时未收到响应则响应无效（QozeCode 侧已忽略）——无需显式 NACK。

---

## 4. 错误处理与降级矩阵

| 故障场景 | 检测方式 | 行为 |
|---------|---------|------|
| App 未启动 | QozeCode connect 失败 | `enabled=False`，全流程静默，纯终端体验 |
| App 运行中被杀 | socket 写失败 (EPIPE) | 关闭连接，静默降级；不重连 |
| QozeCode 被 kill -9 | App 侧 socket EOF | 移除会话，若该会话有待批准 UI 一并清除 |
| 消息 JSON 解析失败 | framer/Codable 异常 | 丢弃该行，记 debug 日志，不断连 |
| 未知消息 type | switch default | 忽略（向前兼容） |
| socket 文件残留（上次异常退出） | App 启动 bind 前检查 | `unlink` 旧文件后重新 bind |
| 通知权限被拒 | UNUserNotificationCenter 设置回调 | 降级为纯图标提醒 |

---

## 5. 性能与资源预算

| 指标 | 预算 | 依据 |
|------|------|------|
| App 常驻内存 | < 60 MB | 参照同类菜单栏 App（Stats ~40MB） |
| App CPU（空闲） | ≈ 0% | 纯事件驱动，无轮询 |
| 图标动画 | 5fps 离散帧，仅非 idle 时运行 | 菜单栏刷新节流限制 |
| 消息吞吐 | < 10 msg/s/会话 | 状态迁移频率上限，队列 256 充足 |
| Popover 打开延迟 | < 100ms | SessionStore 内存态，无 IO |

---

## 6. 开放问题（需在 M1/M2 验证）

| # | 问题 | 验证时点 |
|---|------|---------|
| 1 | ~~图标动画方案~~ ✅ 已解决（M1 实现期）：采用 SF Symbols `.symbolEffect`（thinking/waiting_approval 脉冲呼吸、executing 旋转），系统级渲染，无需 AppKit 桥接，不受菜单栏节流影响 | M1 ✅ |
| 2 | `.timeSensitive` 通知中断级别 entitlement 需要完整签名配置，ad-hoc 本地构建下不可用 → V1 直接使用普通级别通知，M2 验证提醒强度是否足够 | M2 |
| 3 | ~~IDEA 系窗口激活粒度~~ ✅ 已解决（v0.4）：QozeCode 沿进程树探测最近 GUI 祖先并上报 `host_app_pid`，IDEA/VSCode 用 `NSRunningApplication.activate`（无权限弹窗），iTerm2/Terminal 用 AppleScript 按 tty 精确到 tab | M3 ✅ |
| 4 | ~~App 后启动/重启的会话重连~~ ✅ 已解决（v0.3.1）：Reporter 周期重连 + 最新状态补发 | M1 ✅ |

---

## 7. 目录结构规划

```
QozeCode 仓库:
├── macos/
│   ├── build_island.sh              # xcodebuild 本地构建 + 拷贝到 ~/Applications（ad-hoc 签名）
│   ├── uninstall_island.sh          # 卸载 App + LaunchAgent
│   ├── com.qoze.code.plist        # LaunchAgent 模板（可选自启）
│   └── QozeCode/                  # App 源码 (swiftc 直接编译, 无 xcodeproj)
│       ├── Info.plist               # LSUIElement=true (无 Dock 图标)
│       └── Sources/
│           ├── QozeCodeApp.swift      # @main, MenuBarExtra 入口
│           ├── SessionStore.swift       # 状态仓库 (@MainActor @Observable)
│           ├── Server/
│           │   ├── IslandServer.swift   # POSIX UDS server (v0.3 修正, 见 §2.2)
│           │   └── Messages.swift       # Codable 协议模型
│           ├── UI/
│           │   ├── MenuBarIcon.swift    # 状态→SF Symbol 映射
│           │   └── PopoverView.swift    # 会话列表面板
│           └── Services/
│               └── NotificationService.swift  # UNUserNotificationCenter
└── utils/island_reporter.py         # QozeCode 侧唯一新增文件（+ 各处 hook 埋点）
```

**仓库策略**: App 源码放 QozeCode 仓库 `macos/QozeCode/` 子目录——
协议模型双端同仓演进，避免跨仓库版本漂移；源码分发 + 本地构建，无独立发布流程。
