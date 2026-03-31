# Feishu QQ LLM Bot

飞书 + QQ 双平台 AI 机器人，基于 OpenAI 兼容 API 实现多轮对话、工具调用与长期记忆。

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 目录

- [功能特性](#功能特性)
- [快速开始](#快速开始)
  - [环境要求](#环境要求)
  - [本地安装](#本地安装)
  - [Docker 部署](#docker-部署)
- [详细配置](#详细配置)
  - [最小配置示例](#最小配置示例)
  - [完整配置说明](#完整配置说明)
- [平台接入指南](#平台接入指南)
  - [飞书接入](#飞书接入)
  - [QQ 接入](#qq-接入)
- [开发自定义技能](#开发自定义技能)
- [项目结构](#项目结构)
- [API 端点](#api-端点)
- [常见问题](#常见问题)
- [许可证](#许可证)

---

## 功能特性

| 特性 | 说明 |
|------|------|
| **双平台接入** | 同时支持飞书 Lark 和 QQ 开放平台，统一代码管理 |
| **模型兼容** | 支持任何 OpenAI 兼容接口（NewAPI、OneAPI、DeepSeek、Gemini 等） |
| **工具调用** | 内置联网搜索、长期记忆检索，支持自定义插件扩展 |
| **记忆系统** | 短期窗口记忆 + Chroma 向量长期记忆，支持语义检索 |
| **异步架构** | FastAPI + asyncio，支持高并发 Webhook 处理 |
| **Docker 支持** | 一键部署，包含 ChromaDB 向量数据库 |

---

## 快速开始

### 环境要求

- Python 3.9+
- 飞书自建应用 或 QQ 机器人账号
- OpenAI 兼容的 LLM API 密钥

### 本地安装

#### 1. 克隆仓库

```bash
git clone <仓库地址>.git
cd feishu-qq-llm-bot
```

#### 2. 创建虚拟环境

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

#### 4. 配置应用

```bash
# 复制配置模板
cp config/config-example.yaml config/config.yaml

# 编辑配置（必填项见下文）
# Windows: notepad config/config.yaml
# macOS/Linux: vim config/config.yaml
```

#### 5. 启动服务

```bash
python src/main.py
```

服务启动后将监听 `http://0.0.0.0:8080`，测试访问：

```bash
curl http://localhost:8080/
# {"status":"running","service":"Feishu + QQ Bot","version":"1.0.0"}
```

### Docker 部署

适合生产环境，自动包含 ChromaDB 向量数据库。

```bash
# 1. 准备配置（注意修改 database.chroma_host 为 chromadb）
cp config/config-example.yaml config/config.yaml

# 2. 启动所有服务
docker compose up -d

# 3. 查看日志
docker compose logs -f bot
```

---

## 详细配置

配置文件路径：`config/config.yaml`

### 最小配置示例

仅启用基础功能所需的最少配置：

```yaml
server:
  port: 8080
  debug: false

feishu:
  app_id: "cli_xxxxx"          # 飞书自建应用 ID
  app_secret: "xxxxxxxx"        # 飞书应用密钥

qq:
  app_id: "1234567890"          # QQ 机器人 ID
  client_secret: "xxxxxxxx"     # QQ 机器人密钥

openclaw:
  api_url: "https://api.openai.com/v1"  # LLM API 地址
  api_key: "sk-xxxxxxxx"                 # LLM API 密钥
  model: "gpt-4o-mini"                   # 模型名称
  enable_tools: true                     # 启用工具调用

memory:
  short_term_max_messages: 6    # 短期记忆保留的消息轮数
```

### 完整配置说明

<details>
<summary>点击查看完整配置说明</summary>

```yaml
server:
  port: 8080                    # 服务端口（QQ 仅支持 80/443/8080/8443）
  debug: true                   # 调试模式：打印详细日志

feishu:
  app_id: ""                    # 飞书自建应用 ID（以 cli_ 开头）
  app_secret: ""                # 飞书应用密钥
  verification_token: ""        # 可选：事件订阅验证令牌
  event_encrypt_key: ""         # 可选：事件加密密钥

qq:
  app_id: ""                    # QQ 机器人 AppID
  client_secret: ""             # QQ 机器人 AppSecret
  sandbox: false                # 沙箱模式（测试环境设为 true）
  verify_signature: true        # 启用 Webhook 签名验证（生产环境务必开启）

openclaw:
  api_url: ""                   # OpenAI 兼容 API 地址
  api_key: ""                   # API 密钥
  model: "deepseek-chat"        # 模型名称
  enable_tools: true            # 启用工具调用（Function Calling）
  max_tool_rounds: 5            # 最大工具调用轮数

memory:
  short_term_max_messages: 6    # 短期记忆窗口大小
  store_each_turn_in_vector: false  # 每轮对话都存入向量库（除总结外）

system_prompt: |                  # 系统提示词，定义 AI 角色和行为
  你是一个拥有长期记忆与联网检索能力的实用 AI 助手。
  在需要事实核查或最新信息时，应主动调用 web_search；
  在需要回忆历史约定时，可调用 recall_long_term_memory。
  系统已预检索部分相关记忆片段，请与工具结果一并参考。

database:
  chroma_host: "127.0.0.1"      # ChromaDB 地址（Docker 部署时用 chromadb）
  chroma_port: 8000             # ChromaDB 端口

skills:
  enable_plugins: true          # 启用插件系统
  disable_plugins: []           # 禁用的插件列表
  extra_modules: []             # 额外的技能模块路径

search:
  provider: auto                # 搜索提供商：auto/tencent_wsa/ddgs

tencent_wsa:
  enabled: false              # 腾讯云 WSA 搜索（需腾讯云账号）
  secret_id: ""
  secret_key: ""
  endpoint: "wsa.tencentcloudapi.com"
  region: ""
  mode: 0
  timeout_seconds: 30
```

</details>

---

## 平台接入指南

### 飞书接入

#### 1. 创建应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 点击「开发者后台」→「创建企业自建应用」
3. 记录 **App ID** 和 **App Secret**

#### 2. 配置权限

进入应用详情页，添加以下权限：

| 权限 | 用途 |
|------|------|
| `im:chat:readonly` | 读取会话信息 |
| `im:message:send` | 发送单聊消息 |
| `im:message.group_msg` | 发送群聊消息 |

添加后点击「发布版本」并申请发布。

#### 3. 配置事件订阅

1. 左侧菜单「事件与回调」→「事件订阅」
2. 开启「加密策略」（可选但推荐）
3. **请求地址**：`https://你的域名/webhook/feishu`
4. 添加订阅事件：`im.message.receive_v1`
5. 保存配置，验证通过即可

#### 4. 本地开发调试

使用 ngrok 暴露本地服务：

```bash
ngrok http 8080
# 获得 https://xxxx.ngrok-free.app
# 填入飞书控制台: https://xxxx.ngrok-free.app/webhook/feishu
```

---

### QQ 接入

#### 1. 注册机器人

1. 访问 [QQ 开放平台](https://bot.q.qq.com/)
2. 创建机器人，选择「纯 Webhook 模式」
3. 记录 **AppID** 和 **AppSecret**

#### 2. 配置回调地址

QQ 要求回调地址必须使用 **HTTPS** 且端口为 **80/443/8080/8443** 之一。

**回调地址**：`https://你的域名/webhook/qq`

#### 3. 本地开发调试

同样使用 ngrok 暴露 HTTPS 地址：

```bash
ngrok http 8080
# 获得 https://xxxx.ngrok-free.app
# 填入 QQ 控制台回调地址: https://xxxx.ngrok-free.app/webhook/qq
```

> ⚠️ **注意**：QQ Webhook 验签要求 `qq.verify_signature: true`，确保 `client_secret` 与控制台一致。

---

## 开发自定义技能

在 `src/skills/plugins/` 目录创建新的技能文件，例如 `my_skill.py`：

```python
"""我的自定义技能：获取天气信息。"""
from __future__ import annotations
from typing import Any

# 工具定义：描述技能功能，供 LLM 决策调用
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的当前天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如北京、上海"}
                },
                "required": ["city"]
            }
        }
    }
]


async def run_tool(name: str, args: dict, *, chat_id: str, vector_query_fn) -> str | None:
    """执行工具调用。
    
    Args:
        name: 工具名称
        args: 工具参数
        chat_id: 当前对话 ID
        vector_query_fn: 向量查询函数（用于检索记忆）
    
    Returns:
        工具执行结果，或 None（不处理该工具）
    """
    if name != "get_weather":
        return None
    
    city = args.get("city", "")
    # 这里调用真实的天气 API
    return f"{city} 今天晴天，气温 25°C，空气质量优。"
```

重启服务后，AI 将自动识别并使用这个新技能。

详细开发指南：[SKILL_DEVELOPMENT.md](docs/SKILL_DEVELOPMENT.md)

---

## 项目结构

```
feishu-qq-llm-bot/
├── config/
│   ├── config-example.yaml      # 配置模板
│   └── config.yaml              # 实际配置文件（需手动创建）
├── docs/
│   └── SKILL_DEVELOPMENT.md     # 技能开发文档
├── src/
│   ├── channels/                # 平台适配层（Webhook 处理）
│   │   ├── feishu_handler.py    # 飞书消息处理器
│   │   ├── qq_handler.py        # QQ 消息处理器
│   │   └── qq_crypto.py         # QQ 签名验证
│   ├── core/                    # 核心逻辑层
│   │   ├── agent.py             # AI 对话管理（核心）
│   │   ├── config.py            # 配置读取
│   │   ├── logger.py            # 日志配置
│   │   ├── memory.py            # 短期记忆管理
│   │   └── vector_memory.py     # 向量长期记忆
│   ├── skills/                  # 技能系统（工具/插件）
│   │   ├── builtin_tools.py     # 内置工具（搜索、记忆等）
│   │   ├── registry.py          # 技能注册表
│   │   ├── tools.py             # 工具执行器
│   │   └── plugins/             # 自定义插件目录
│   │       ├── __init__.py
│   │       └── example_time.py  # 示例：获取时间
│   └── main.py                  # 应用主入口
├── docker-compose.yml           # Docker 编排配置
├── requirements.txt             # Python 依赖
└── README.md                    # 本文件
```

---

## API 端点

| 方法 | 路径 | 说明 | 来源平台 |
|------|------|------|----------|
| GET | `/` | 健康检查，返回服务状态 | - |
| POST | `/webhook/feishu` | 飞书事件订阅回调 | 飞书开放平台 |
| POST | `/webhook/qq` | QQ Webhook 回调 | QQ 开放平台 |

---

## 常见问题

<details>
<summary><b>Q: 飞书收到消息但无回复？</b></summary>

**可能原因及解决：**

1. **配置错误**：检查 `config.yaml` 中的 `feishu.app_id` 和 `feishu.app_secret` 是否与飞书控制台一致
2. **权限未开通**：确认已在飞书后台添加 `im:message:send` 权限并发布版本
3. **查看日志**：运行 `docker compose logs -f bot` 查看是否有错误信息
4. **Webhook 未验证**：检查飞书控制台事件订阅地址是否正确，点击「验证」按钮测试连通性

</details>

<details>
<summary><b>Q: QQ Webhook 验签失败？</b></summary>

**可能原因及解决：**

1. **密钥错误**：确认 `qq.client_secret` 与 QQ 开放平台控制台中的 AppSecret 完全一致
2. **签名验证关闭**：本地调试时可设置 `qq.verify_signature: false`，但**生产环境务必开启**
3. **时间不同步**：确保服务器时间与标准时间同步（误差需小于 5 分钟）

</details>

<details>
<summary><b>Q: 长期记忆不生效？</b></summary>

**可能原因及解决：**

1. **ChromaDB 未连接**：检查日志是否有连接错误，Docker 部署时确保 `database.chroma_host: chromadb`
2. **自动降级**：ChromaDB 连接失败时会自动降级为仅短期记忆，不会报错
3. **强制写入**：设置 `memory.store_each_turn_in_vector: true` 强制每轮对话写入向量库

</details>

<details>
<summary><b>Q: 模型返回"工具调用次数过多"？</b></summary>

**解决方法：**

1. 增加调用次数限制：调大 `openclaw.max_tool_rounds`（默认 5，可适当增加）
2. 简化问题：减少单轮对话中的工具依赖，分多次提问
3. 优化提示词：在系统提示词中引导 AI 减少不必要的工具调用

</details>

---

## 许可证

[MIT License](LICENSE)

---

<p align="center">
  Made with ❤️ | 有问题欢迎提 Issue 或 PR
</p>
