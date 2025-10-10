# QozeCode Agent

<img src="./assets/logo.png" alt="图片描述" style="padding: 60px;">

```QozeCode Agent``` 是一个功能强大的AI编程助手，集成了多种AI模型和实用工具，为开发者提供智能化的编程支持和自动化能力。

- **多模型支持**: 支持 ```Claude、Gemini、GPT、DeepSeek``` 官方等多种主流AI模型
- **丰富工具集**: 多种MCP工具使用(coming soon)，文件操作、命令执行、网络搜索等工具
- **可扩展架构**: 模块化设计，易于添加新功能和工具
- **私有模型key**: 使用个人自己的模型key，在成本和隐私性方面会较好一些

#### 目前集成模型厂商

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

### 核心功能特性

#### 📊 办公自动化

- **Excel 智能处理**: Agent 可以帮助你自动化处理 Excel 文件，包括数据分析、表格生成、公式计算等操作
- **邮件智能分析**: 支持 macOS 自带邮件客户端集成，可以帮你阅读、分析和总结邮件内容，提取关键信息

#### 🌐 浏览器自动化

- **网页操作**: 智能浏览器控制功能，可以自动化网页操作和数据抓取
- **持续更新**: 浏览器操作功能将持续更新上线，带来更多自动化可能性

#### 🛠 开发工具集

- **文件操作**: 智能文件管理和批量处理
- **命令执行**: 安全的系统命令执行和自动化脚本运行
- **网络搜索**: 集成搜索引擎，快速获取开发相关信息
- **数学计算**: 内置数学工具，支持复杂计算和数据处理

#### 🔧 扩展能力

- **MCP 工具支持**: 即将支持更多 Model Context Protocol 工具（coming soon）
- **API 集成**: 跟多高效有价值的工具会通过API持续集成

##### 最佳使用建议

> 如果你考虑性价比并且还是国内用户， 建议你选择 ' deepseek ' 作为你的首选模型使用

##### 使用演示

[演示视频](./assets/video.mp4)

# QuickStart

## 安装方式

### 方式一：通过脚本+源码自动构建

- 1、下载源码在本地构建：二进制文件

```bash
curl -fsSL https://raw.githubusercontent.com/KylinShinlyLin/QozeCode/main/install.sh | bash -s uninstall
```

- 2、 构建完成后手动添加到环境变量中

```bash
source ~/.qoze/qoze_env.sh && qoze
```
<br><br>

### 方式二：通过 Homebrew 安装（目前兼容有点问题）

1. 添加 tap 源：

```bash
brew tap KylinShinlyLin/qoze https://github.com/KylinShinlyLin/homebrew-qoze
```

2. 安装 QozeCode：

```bash
brew install qoze
```

### 更新或重新安装

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

### brew 安装遇到-授权证书问题

```bash
# 1. 临时禁用 Gatekeeper
sudo spctl --master-disable

# 2. 执行你的安装命令
brew cleanup qoze
brew untap KylinShinlyLin/qoze
brew tap KylinShinlyLin/qoze https://github.com/KylinShinlyLin/homebrew-qoze
brew install qoze

# 3. 重新启用 Gatekeeper（重要！）
sudo spctl --master-enable
```

### 使用方法

安装完成后，在终端中直接运行：

```bash
qoze
```

## 许可证

本项目采用 Apache License 2.0 开源协议。详情请参阅 [LICENSE](LICENSE) 文件。

Copyright 2025 QozeCode

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

