# Contributing

感谢你对 LiteLLM CN Console 的关注。

## 提交 Issue

提交 Issue 时建议包含：

- 使用场景
- 复现步骤
- 期望行为
- 实际行为
- LiteLLM 版本
- Python 版本
- 部署方式

如果是界面问题，建议附上截图。

## 提交 Pull Request

建议流程：

1. Fork 仓库并创建功能分支
2. 保持改动范围尽量单一
3. 提交前自测
4. 更新 README 或示例配置（如果有用户可见改动）
5. 发起 Pull Request

## 代码约定

- Python 代码保持清晰可读
- 前端尽量维持当前轻量、中文化风格
- 不要提交真实密钥、密码、日志和本地环境文件
- 新增配置时同步更新 `env.simple_ui.example`

## 本地开发

```bash
pip install -r requirements.txt
cp env.simple_ui.example env.simple_ui
source env.simple_ui
uvicorn app:app --reload --host 0.0.0.0 --port 4040
```

## 安全注意事项

- 不要把真实 `LITELLM_MASTER_KEY` 提交到仓库
- 不要把 `env.simple_ui`、日志目录或调试输出提交到仓库
- 如果改动涉及管理接口，请优先确认不会放大 LiteLLM 权限暴露面
