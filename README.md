# API2Cursor Next

面向个人用户的轻量 Cursor 模型网关，直接运行 LiteLLM Proxy 与 PostgreSQL，不包含自建 Web、Nginx 或前端依赖。

提供：

- LiteLLM 官方管理后台
- Cursor Ask、Plan 和 Agent 接口
- OpenAI 兼容接口
- 模型与上游管理
- Virtual Key、预算、速率和用量记录
- 本地 Docker Compose 与雨云部署配置

## 快速开始

Windows PowerShell：

```powershell
.\scripts\init.ps1
docker compose up -d --build
```

Linux 或 macOS：

```sh
./scripts/init.sh
docker compose up -d --build
```

启动后：

- 管理后台：`http://localhost:3029/ui/`
- 健康检查：`http://localhost:3029/health/readiness`
- Cursor Base URL：`http://localhost:3029/cursor`

后台用户名为 `admin`，密码是 `.env` 中的 `LITELLM_MASTER_KEY`。

## 文档

完整的本地部署、雨云部署、后台模型配置、Responses-only 上游、Virtual Key、Cursor 接入、Agent 工具验证、备份升级、安全要求和已知问题，请阅读：

**[完整配置与故障排查](docs/configuration.md)**

使用 Responses-only 上游时，不要只测试 `/v1/responses`。必须按照文档配置 `openai/responses/` 桥接，并用 `/v1/chat/completions` 验证 Cursor 实际路径。

## 项目检查

```sh
node tests/check-static.mjs
docker compose config --quiet
docker compose -f rainyun-compose.yml config --no-interpolate --quiet
docker build -t api2cursor-next-litellm ./litellm
```

## 许可证

[MIT](LICENSE)
