# QozeCode Agent

<img src="./assets/logo.png" alt="图片描述" style="padding: 60px;">

```QozeCode Agent``` 是一个功能强大的AI编程助手，集成了多种AI模型和实用工具，为开发者提供智能化的编程支持和自动化能力。

- **多模型支持**: 支持 ```Claude、Gemini、GPT、DeepSeek``` 官方等多种主流AI模型
- **丰富工具集**: 多种MCP工具使用(coming soon)，文件操作、命令执行、网络搜索等工具
- **可扩展架构**: 模块化设计，易于添加新功能和工具
- **私有模型key**: 使用个人自己的模型key，在成本和隐私性方面会较好一些

### 目前集成模型厂商

| 模型       | 厂商                   |
|----------|----------------------|
| Claude-4 | aws bedrock          |
| GPT-5    | openai 官方            |
| DeepSeek | deepseek 官方          |
| Gemini   | gcp Vertex AI (正在开发) |
| ollama   | 自部模型集成（正在开发）         |

> 为什么不全模型集成？
>> 在测试 Agent 期间发现，全模型支持，必然会放弃一些高阶模型本身的能力而去兼容一些能力不足的模型，为了保证最佳使用体验，通过个人体验分析后，选择性的择优一些模型集成。
> > 如果您有特殊的需要可以提出 Issues ，我会尽快和您联系沟通

## 核心功能特性

### 📊 办公自动化

- **Excel 智能处理**: Agent 可以帮助你自动化处理 Excel 文件，包括数据分析、表格生成、公式计算等操作
- **邮件智能分析**: 支持 macOS 自带邮件客户端集成，可以帮你阅读、分析和总结邮件内容，提取关键信息

### 🌐 浏览器自动化

- **网页操作**: 智能浏览器控制功能，可以自动化网页操作和数据抓取
- **持续更新**: 浏览器操作功能将持续更新上线，带来更多自动化可能性

### 🛠 开发工具集

- **文件操作**: 智能文件管理和批量处理
- **命令执行**: 安全的系统命令执行和自动化脚本运行
- **网络搜索**: 集成搜索引擎，快速获取开发相关信息
- **数学计算**: 内置数学工具，支持复杂计算和数据处理

### 🔧 扩展能力

- **MCP 工具支持**: 即将支持更多 Model Context Protocol 工具（coming soon）
- **API 集成**: 跟多高效有价值的工具会通过API持续集成

### 最佳使用建议

> 如果你考虑性价比并且还是国内用户， 建议你选择 ' deepseek ' 作为你的首选模型使用

### 使用演示
[video.mp4](assets%2Fvideo.mp4)

## QuickStart

### 安装方式

#### 方式一：通过 Homebrew 安装（推荐）

1. 添加 tap 源：

```bash
brew tap KylinShinlyLin/qoze https://github.com/KylinShinlyLin/homebrew-qoze
```

2. 安装 QozeCode：

```bash
brew install qoze
```

#### 更新或重新安装

如果需要更新或重新安装，可以执行以下命令：

```bash
# 清理旧版本
brew cleanup qoze

# 移除旧的 tap 源（如果存在）
brew untap KylinShinlyLin/qoze

# 重新添加 tap 源
brew tap KylinShinlyLin/qoze https://github.com/KylinShinlyLin/homebrew-qoze

# 安装最新版本
brew install qoze
```

### 使用方法

安装完成后，在终端中直接运行：

```bash
qoze
```

首次运行时，系统会引导你进行基本配置，包括选择AI模型和设置API密钥等。

