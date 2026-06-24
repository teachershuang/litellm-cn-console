# LiteLLM CN Console

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LiteLLM](https://img.shields.io/badge/LiteLLM-Gateway-orange)](https://github.com/BerriAI/litellm)
[![License](https://img.shields.io/badge/License-MIT-black)](#license)

一个面向 **LiteLLM** 的简化中文管理台，聚焦中文团队最常用的 4 类能力：

- 注册和删除模型
- 创建和查看虚拟密钥
- 查看分时 / 分日 / 分密钥用量统计
- 查看单次请求日志

它的目标不是替代 LiteLLM 原生后台，而是提供一个更轻、更中文化、更适合内部运维和业务同学使用的前台入口。

## 仓库建议

- 仓库名：`litellm-cn-console`
- 中文简介：`一个面向 LiteLLM 的简化中文管理台，提供模型注册、密钥管理、用量统计与请求日志查看，适合本地模型网关和小团队内部使用。`
- 英文简介：`A simplified Chinese admin console for LiteLLM, focused on model registration, virtual key management, usage analytics, and request logs.`

## 适用场景

- 你已经有一套 LiteLLM 网关
- 原生管理页对业务团队来说过于复杂
- 你希望用中文界面管理模型、密钥和基础统计
- 你需要一个轻量、可二次开发的内部控制台

## 当前功能

### 1. 登录与会话

- 用户名密码登录
- 基于 `SessionMiddleware` 的简单会话管理

### 2. 模型管理

- 查看当前 LiteLLM 中的模型列表
- 通过 `/model/new` 注册 OpenAI 兼容上游模型
- 通过 `/model/delete` 删除数据库型模型记录

适用于：

- 本地 `vLLM`
- 自建 OpenAI 兼容服务
- 线上 Qwen / OpenAI 风格 API

### 3. 密钥管理

- 创建虚拟密钥
- 查看密钥别名、模型范围、花费、到期时间

### 4. 用量看板

- 分时请求量
- 分日 Token 总量
- 按密钥请求量 Top 10
- 请求总数 / Token 总量 / 费用 / 失败数 / 模型数 / 密钥数

### 5. 请求日志

- 按时间范围拉取 LiteLLM `spend/logs/v2`
- 展示时间、模型、密钥、状态、Token、费用、耗时、请求 ID、错误信息

## 技术栈

- Python 3.10+
- FastAPI
- Jinja2
- 原生 HTML / CSS / JavaScript
- httpx

## 项目结构

```text
simple_cn_ui/
├─ app.py
├─ requirements.txt
├─ start_simple_cn_ui.sh
├─ env.simple_ui.example
├─ static/
│  ├─ app.js
│  └─ styles.css
└─ templates/
   ├─ index.html
   └─ login.html
```

## 对 LiteLLM 的依赖

本项目不是独立的 LLM 网关，而是 **LiteLLM 的前端控制台**。  
它会调用 LiteLLM 的管理接口，因此你需要先准备好：

- 一个可访问的 LiteLLM Gateway
- LiteLLM `master key`
- 允许访问以下接口：
  - `GET /model/info`
  - `POST /model/new`
  - `POST /model/delete`
  - `GET /key/list`
  - `POST /key/generate`
  - `GET /spend/logs/v2`

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制环境变量示例文件：

```bash
cp env.simple_ui.example env.simple_ui
```

按你的环境修改：

```bash
export SIMPLE_UI_USERNAME='admin'
export SIMPLE_UI_PASSWORD='your-password'
export SIMPLE_UI_SESSION_SECRET='replace-with-random-string'
export SIMPLE_UI_PORT='4040'
export LITELLM_GATEWAY_URL='http://127.0.0.1:4000'
export LITELLM_MASTER_KEY='sk-...'
```

如果你更习惯 `.env` 文件，也可以在自己的部署脚本里转为 `source env.simple_ui` 的方式加载。

### 3. 启动

#### 方式一：直接启动

```bash
source env.simple_ui
uvicorn app:app --host 0.0.0.0 --port ${SIMPLE_UI_PORT:-4040}
```

#### 方式二：用仓库自带脚本

```bash
bash start_simple_cn_ui.sh
```

默认启动后访问：

```text
http://127.0.0.1:4040/login
```

## 与 LiteLLM 集成方式

这套 UI 通过环境变量连接到 LiteLLM：

- `LITELLM_GATEWAY_URL`
  - 例如 `http://127.0.0.1:4000`
- `LITELLM_MASTER_KEY`
  - 用于调用 LiteLLM 管理接口

也就是说：

- LiteLLM 负责模型代理、鉴权、日志和计费
- 本项目负责中文化的管理界面和简化交互

## 已验证的使用方式

适合以下部署组合：

- LiteLLM Gateway + 本地 `vLLM`
- LiteLLM Gateway + 线上 OpenAI 兼容 API
- LiteLLM Gateway + 多模型并行注册

## Docker 运行

### 构建镜像

```bash
docker build -t litellm-cn-console .
```

### 启动容器

```bash
docker run -d \
  --name litellm-cn-console \
  -p 4040:4040 \
  -e SIMPLE_UI_USERNAME=admin \
  -e SIMPLE_UI_PASSWORD=your-password \
  -e SIMPLE_UI_SESSION_SECRET=replace-with-random-string \
  -e LITELLM_GATEWAY_URL=http://host.docker.internal:4000 \
  -e LITELLM_MASTER_KEY=sk-... \
  litellm-cn-console
```

## 还建议继续补的能力

如果准备长期维护，下一步优先建议补这些：

- 截图或 GIF 演示
- `docker-compose.yml`
- 密钥停用 / 删除
- 模型连通性测试
- 请求失败筛选

## 安全说明

- 不建议直接暴露在公网
- 该项目默认是单管理员、轻会话方案
- `LITELLM_MASTER_KEY` 权限较高，应通过受控环境变量注入
- 建议放在内网、VPN 或反向代理鉴权后使用

## 后续可以扩展的方向

- 多管理员和角色权限
- 密钥停用 / 删除 / 预算编辑
- 模型健康检查与连通性测试
- 更细粒度的日志检索
- 导出 CSV / Excel
- Grafana / Prometheus 接入
- 支持组织 / 团队维度统计

## License

本项目使用 [MIT License](./LICENSE)。
