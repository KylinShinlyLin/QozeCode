# QozeCode

<div align="center">

**轻量级命令行 AI Agent | 基于 LangGraph 架构 | ReAct 范式**

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/KylinShinlyLin/QozeCode)

[English](#english) | [中文](#中文)

</div>

---

## 中文

## 项目简介

QozeCode 是一个基于 **LangGraph** 架构构建的专业级命令行 AI Agent，通过 **ReAct**（Reasoning and Acting）范式实现复杂开发任务的自动化执行。

作为开发者的智能副驾驶，QozeCode 不仅提供代码生成与审查能力，更能直接与系统 Shell 交互，执行文件操作、系统管理及网络检索，所有操作均在现代化的 TUI（终端用户界面）中呈现。

### 核心亮点

- 🧠 **智能决策引擎**: 基于 LangGraph 状态图的 ReAct 推理框架
- 🌐 **浏览器自动化**: Playwright 驱动的完整 Web 交互能力
- 🎙️ **语音交互**: 实时语音识别与语音指令
- 🖥️ **现代 TUI**: Textual + Rich 打造的沉浸式终端体验
- 🧩 **技能系统**: 可扩展的领域专家插件架构
- 🔌 **多模型支持**: 集成 7+ 主流 LLM 厂商

### 支持模型矩阵

QozeCode 深度集成了全球领先的 AI 模型厂商，为不同场景提供最佳算力支持：

| 厂商 (Provider)     | 支持模型 (Supported Models)               | 特性描述                   |
|:------------------|:--------------------------------------|:-----------------------|
| **OpenAI**        | `GPT-5.2` / `GPT-5.4`                 | 强大的通用推理与代码生成能力         |
| **DeepSeek**      | `DeepSeek Chat` / `DeepSeek Reasoner` | 卓越的推理性能与高性价比，支持深度思考    |
| **Google**        | `Gemini 3.1 Pro` / `Gemini 3 Flash`   | 谷歌最新多模态模型，响应速度极快       |
| **xAI**           | `Grok 4.1 Fast`                       | 极速推理，专注于实时信息处理         |
| **Zhipu AI**      | `GLM-4.6` / `GLM-5` / `GLM-5V Turbo`  | 优秀的中文理解能力与工具调用表现       |
| **Alibaba Cloud** | `Qwen 3 Max`                          | 通义千问最新旗舰，具备强大的逻辑思维能力   |
| **Moonshot**      | `Kimi K2.5` / `Kimi for Coding`       | 月之暗面双模型：K2.5 通用能力强，Coding 专为编程优化 |
| **LiteLLM**       | `GPT-5.2` / `GPT-5.4` / `GPT-5.2-chat-latest` | 支持自定义 API 端点      |

## 核心特性

### 🧠 智能决策引擎

基于 LangGraph 状态图构建的决策核心，支持复杂的任务规划与多步推理。系统严格遵循 ReAct 模式，确保每一个操作都经过"思考-决策-执行-观察"的完整闭环，保证任务执行的准确性与可控性。

**关键特性**:
- Prompt Caching 优化（静态/动态提示词分离）
- 流式输出实时展示推理过程
- 完整的工具调用链追踪
- 智能错误恢复与重试机制

### 🌐 沉浸式浏览器操作

QozeCode 具备完整的浏览器自动化控制能力，打破了传统终端工具的界限。

<p align="center"><img src="./assets/浏览器演示.gif" width="800"></p>

- **全功能交互**: 不仅能阅读网页，还能像人类一样点击按钮、填写表单、滚动页面
- **多标签页管理**: 支持同时打开多个标签页，并在不同页面间灵活切换
- **智能阅读**: 自动将网页内容转换为 Markdown 格式，提取核心信息
- **自动化工作流**: 通过自然语言指令完成数据采集、自动化测试等复杂操作

### 🎙️ 智能语音交互

QozeCode 支持通过语音与 AI 直接对话，带来更自然、高效的交互体验。

<p align="center"><img src="./assets/audio.gif" width="800"></p>

- **实时语音识别**: 基于 Soniox 的高性能语音转文本，无延迟指令输入
- **专有名词定制**: 根据项目环境自动校准上下文，提升专业术语识别率
- **免提编码**: 解放双手，随时通过语音下达复杂的开发任务

### 🖥️ 沉浸式终端体验

采用 **Textual** 与 **Rich** 框架打造的现代化终端界面：

- **语法高亮**: 支持多种编程语言的代码高亮
- **流式输出**: 实时展示 Agent 思考与执行过程
- **面板分割**: 多区域布局，信息一目了然
- **快捷操作**: 支持键盘快捷键与交互式选择

### 🧩 模块化技能系统

拥有可扩展的技能（Skill）架构，支持按需加载专业领域的知识库与工具集：

**内置技能**:
- `ui-ux-pro-max`: UI/UX 设计专家，支持 50+ 设计风格
- `ppt-generator`: 一键生成乔布斯风极简科技感演示稿
- `explain-code`: 可视化图表和类比解释代码
- `weather`: 实时天气与天气预报

**自定义技能**: 您可以在 `~/.qoze/skills/` 目录下创建自定义技能，让 Agent 秒变特定领域专家。

### 🛠️ 全栈工具集成

内置多维度系统工具链，打破模型与操作系统的壁垒：

#### 核心工具
- **文件操作**: 读取、写入、搜索、批量处理文件
- **命令执行**: 安全执行 Shell 命令，支持实时输出
- **网络搜索**: 集成 Tavily API，实时网络信息检索
- **URL 读取**: 网页内容提取与 Markdown 转换
- **飞书文档**: 支持读取飞书文档内容

#### 高级工具
- **浏览器自动化**: 基于 Playwright 的完整 Web 交互
- **语音识别**: 实时语音转文本
- **PDF 处理**: PDF 文档解析与内容提取
- **技能管理**: 激活、停用、安装技能

## 项目架构

### 技术栈

- **核心框架**: LangGraph (状态图) + LangChain (LLM 集成)
- **TUI 框架**: Textual + Rich
- **浏览器自动化**: Playwright
- **语音识别**: Soniox
- **构建工具**: setuptools


## 环境要求

- **操作系统**: macOS / Linux
- **Python 版本**: >= 3.9
- **终端环境**: 支持 True Color 的终端模拟器 (推荐 iTerm2, Alacritty)
- **可选依赖**: Playwright (浏览器自动化)

## 快速开始

### 1. 安装

#### 🚀 方式一：一键安装 (推荐)

```bash
curl -fsSL https://raw.githubusercontent.com/KylinShinlyLin/QozeCode/main/install.sh | bash -s install
```

#### 📦 方式二：手动安装

```bash
# 1. 克隆仓库
git clone https://github.com/KylinShinlyLin/QozeCode.git
cd QozeCode

# 2. 运行安装脚本
chmod +x install.sh
./install.sh
```

### 2. 配置

QozeCode 依赖配置文件管理 API 密钥与模型参数：

```bash
# 配置文件路径优先级：/etc/conf/qoze.conf > ~/.qoze/qoze.conf
cp qoze.conf.template ~/.qoze/qoze.conf
```

编辑配置文件，填入您的 API Key：

```ini
[OpenAI]
api_key=your_openai_api_key

[DeepSeek]
api_key=your_deepseek_api_key

[Kimi]
api_key=your_moonshot_api_key
base_url=https://api.moonshot.cn/v1

[KimiCode]
api_key=your_kimi_coding_api_key
base_url=https://api.kimi.com/coding/v1

[tavily]
tavily_key=your_tavily_api_key

[soniox]
api_key=your_soniox_api_key
```

### 3. 启动

```bash
python qoze_tui.py
```

首次启动会提示选择模型，后续可通过配置文件修改。

## 开发指南

### 新增工具

1. 在 `tools/` 目录下创建新文件 `new_tool.py`
2. 实现工具函数并添加类型注解和文档字符串
3. 在 `qoze_code_agent.py` 中导入并注册工具
4. 在 `utils/system_prompt.py` 中添加工具使用说明

### 新增模型支持

1. 在 `enums.py` 中添加 `ModelProvider` 和 `ModelType` 枚举
2. 在 `model_initializer.py` 中添加模型初始化逻辑
3. 在 `config_manager.py` 中添加凭证检查
4. 在 `launcher.py` 中添加模型选择选项
5. 更新 `qoze.conf.template`

### 创建自定义技能

在 `~/.qoze/skills/` 目录下创建技能目录，包含 `SKILL.md` 文件：

```text
~/.qoze/skills/my-skill/
└── SKILL.md
```

SKILL.md 格式：

```markdown
# 技能名称

技能描述...

## 使用场景
- 场景1
- 场景2
```

## 项目导航

详细的项目导航规则和 Agent 工作指南，请参考：[.qoze/rules/project-navigation.md](.qoze/rules/project-navigation.md)

该文档包含：
- 模块索引与职责说明
- 代码定位规则
- 关键调用链
- 高风险区域与禁止误改清单
- 开发工作流程

## 常见问题

### 1. 浏览器自动化不工作？

确保已安装 Playwright 和浏览器：

```bash
pip install playwright
playwright install
```

### 2. 语音识别不工作？

确保已配置 Soniox API Key 并安装 PyAudio：

```bash
pip install pyaudio
```

### 3. 模型初始化失败？

检查配置文件中的 API Key 是否正确，确保配置文件路径正确。

## 贡献指南

欢迎贡献代码、报告问题或提出建议！

1. 提出你的 Issues Fork 本仓库 
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改，标记你的 Issues (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 路线图

- [ ] 支持更多 LLM 厂商
- [ ] 增强 Agent 记忆能力
- [ ] 支持多 Agent 协作
- [ ] 提供 Web UI
- [ ] 支持插件市场

## 许可证

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
