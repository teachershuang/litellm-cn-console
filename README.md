# LiteLLM CN Console

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LiteLLM](https://img.shields.io/badge/LiteLLM-Gateway-orange)](https://github.com/BerriAI/litellm)
[![License](https://img.shields.io/badge/License-MIT-black)](./LICENSE)

一个面向 LiteLLM 的简化中文管理台，提供模型注册、虚拟密钥管理、用量统计与请求日志查看，适合本地模型网关和小团队内部使用。

> A simplified Chinese admin console for LiteLLM, focused on model registration, virtual key management, usage analytics, and request logs.

## 界面截图

### 使用统计

![使用统计](./docs/dashboard.png)

### 登录页

![登录页](./docs/login.png)

## 功能

- 中文登录页和中文控制台界面
- 查看 LiteLLM 当前模型列表
- 注册 OpenAI 兼容上游模型，本地 vLLM 和云端 API 都可接入
- 创建虚拟密钥，并按密钥统计请求
- 查看分时用量趋势，包含输入、输出、缓存命中、缓存创建和成本
- 查看按密钥、按模型的 Top 用量排行
- 查看单次请求记录，包含状态、输入、输出、缓存、成本、耗时和请求 ID
- 可选演示模式，便于本地预览界面和生成截图

## 工作方式

本项目不是独立网关，而是 LiteLLM Gateway 的轻量中文前台。它通过环境变量连接已有 LiteLLM 服务：

```bash
export LITELLM_GATEWAY_URL='http://127.0.0.1:4000'
export LITELLM_MASTER_KEY='sk-...'
```

当前使用的 LiteLLM 管理接口：

```text
GET  /model/info
POST /model/new
POST /model/delete
GET  /key/list
POST /key/generate
GET  /spend/logs/v2
```

## 对接 LiteLLM

推荐部署方式是让本控制台和 LiteLLM Gateway 运行在同一台内网服务器上。用户访问控制台的地址可以是服务器 IP，例如 `http://192.168.8.29:4040`；控制台在服务器内部访问 LiteLLM，地址写 `http://127.0.0.1:4000`。

### 1. 确认 LiteLLM 已启动

在服务器上执行：

```bash
curl http://127.0.0.1:4000/health/liveliness
```

正常会返回：

```text
"I'm alive!"
```

### 2. 确认 LiteLLM 管理接口可用

```bash
export LITELLM_MASTER_KEY='sk-你的-master-key'

curl -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  http://127.0.0.1:4000/model/info

curl -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  "http://127.0.0.1:4000/key/list?page=1&size=5&return_full_object=true"
```

如果 `/key/list` 或 `/spend/logs/v2` 返回 `Database not connected`、`Prisma Client is not initialized`，需要先修复或重启 LiteLLM 的数据库连接，否则用量统计无法读取历史日志。

### 3. 配置控制台环境变量

在本项目目录创建 `env.simple_ui`：

```bash
export SIMPLE_UI_USERNAME='admin'
export SIMPLE_UI_PASSWORD='请换成强密码'
export SIMPLE_UI_SESSION_SECRET='请换成随机字符串'
export SIMPLE_UI_PORT='4040'

# 生产环境保持 0；只有截图或本地预览才设为 1。
export SIMPLE_UI_DEMO_MODE='0'

# 聚合 /spend/logs/v2 的最大页数。每页 100 条；200 页可覆盖 2 万条日志。
export SIMPLE_UI_MAX_CHART_PAGES='200'

# 和 LiteLLM 同机部署时推荐写 127.0.0.1。
export LITELLM_GATEWAY_URL='http://127.0.0.1:4000'
export LITELLM_MASTER_KEY='sk-你的-master-key'
```

如果服务器上需要指定 Python 解释器，可以加：

```bash
export SIMPLE_UI_PYTHON_BIN='/home/ls/anaconda3/envs/litellm/bin/python'
```

### 4. 启动控制台

```bash
bash start_simple_cn_ui.sh
```

访问：

```text
http://服务器IP:4040/login
```

### 5. 验证统计是否接上真实历史数据

登录后打开“使用统计”。如果历史日志可用，页面不会出现数据库告警，并且 7 天 / 30 天的总请求数、Tokens、成本会来自 LiteLLM 的 `/spend/logs/v2`。

可以用下面的命令直接验证日志接口：

```bash
curl -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  "http://127.0.0.1:4000/spend/logs/v2?start_date=2026-06-01%2000:00:00&end_date=2026-06-30%2023:59:59&page=1&page_size=5&sort_by=startTime&sort_order=desc"
```

控制台统计口径：

- `输入 Tokens`：优先读取 `prompt_tokens` / `input_tokens`
- `输出 Tokens`：优先读取 `completion_tokens` / `output_tokens`
- `缓存命中 Tokens`：读取 `cached_tokens` 或 `prompt_tokens_details.cached_tokens`
- `缓存创建 Tokens`：读取 `cache_creation_input_tokens`
- `推理 Tokens`：读取 `reasoning_tokens` 或 `completion_tokens_details.reasoning_tokens`
- `总成本`：累加 LiteLLM 日志里的 `spend`
- `失败请求`：按日志字段 `status == failure` 统计

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

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

### 3. 启动

```bash
source env.simple_ui
uvicorn app:app --host 0.0.0.0 --port ${SIMPLE_UI_PORT:-4040}
```

也可以使用脚本：

```bash
bash start_simple_cn_ui.sh
```

默认访问：

```text
http://127.0.0.1:4040/login
```

## 演示模式

如果只是想预览界面，不连接真实 LiteLLM，可以开启演示模式：

```bash
export SIMPLE_UI_DEMO_MODE=1
export SIMPLE_UI_USERNAME='admin'
export SIMPLE_UI_PASSWORD='admin'
export SIMPLE_UI_SESSION_SECRET='demo-secret'
export LITELLM_MASTER_KEY='demo'
uvicorn app:app --host 127.0.0.1 --port 4040
```

演示模式只返回内置样例数据，不会注册模型、生成真实密钥或访问真实网关。生产部署不要开启该变量。

## Docker

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

## 项目结构

```text
litellm-cn-console/
├── app.py
├── requirements.txt
├── start_simple_cn_ui.sh
├── env.simple_ui.example
├── Dockerfile
├── docs/
│   ├── login.png
│   └── dashboard.png
├── static/
│   ├── app.js
│   └── styles.css
└── templates/
    ├── index.html
    └── login.html
```

## 安全说明

- 不建议直接暴露在公网
- 建议通过内网、VPN 或反向代理鉴权后访问
- `LITELLM_MASTER_KEY` 权限较高，应通过环境变量安全注入
- 默认实现适合单管理员或小团队内部使用

## 贡献

欢迎提交 Issue 和 Pull Request。提交前建议先阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## Security

如果涉及安全问题，请先阅读 [SECURITY.md](./SECURITY.md)。

## License

本项目使用 [MIT License](./LICENSE)。
