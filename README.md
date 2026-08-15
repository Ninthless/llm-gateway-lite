# API2Cursor Next

轻量、自托管的 Cursor 模型网关。项目直接使用 LiteLLM 官方 `/cursor` 接口支持 Ask、Plan 和 Agent 模式，并提供一个零框架中文接入页。

## 组成

- Nginx：统一暴露 `3029` 端口，提供静态入口并代理流式请求
- LiteLLM Proxy：模型转换、Virtual Key、预算和管理后台
- PostgreSQL：保存模型、密钥和用量数据
- 原生 HTML、CSS、JavaScript：无 npm 依赖、无前端构建步骤

## 快速开始

需要 Docker Desktop 或 Docker Engine，并启用 Compose。

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

打开 `http://localhost:3029`。首次进入管理后台时，使用 `.env` 中的 `LITELLM_MASTER_KEY` 登录，然后添加上游模型并创建 Virtual Key。

## 配置 Cursor

在 Cursor 的模型设置中启用 `Override OpenAI Base URL`，填写：

```text
http://localhost:3029/cursor
```

API Key 填写在 LiteLLM 管理后台创建的 Virtual Key，模型名填写模型配置中的 Public Model Name。分别在 Ask、Plan 和 Agent 模式发起一次请求，确认文本流与工具调用可用。

外网部署时，把 `.env` 中的 `PUBLIC_BASE_URL` 改为实际 HTTPS 地址，例如：

```dotenv
PUBLIC_BASE_URL=https://llm.example.com
```

此时 Cursor Base URL 为 `https://llm.example.com/cursor`。

## 安全

- `.env` 已被 Git 忽略，不要提交任何真实密钥。
- `LITELLM_SALT_KEY` 用于加密数据库中的模型凭据。数据写入后不要更改，否则已有凭据无法解密。
- 项目只映射 Nginx 的 `3029` 端口，LiteLLM 与 PostgreSQL 不直接暴露。
- 公网部署必须在上层配置 HTTPS，并限制管理后台的访问范围。
- 备份时同时保存 PostgreSQL 数据卷和 `LITELLM_SALT_KEY`。

## 版本策略

当前精确固定 `ghcr.io/berriai/litellm-database:v1.97.0-rc.1`。该预发布版本是为了立即使用 LiteLLM 的 Cursor Agent 支持，可能存在尚未稳定的行为。

正式 `v1.97.0` 发布后，应先验证 Ask、Plan、Agent、标准工具、自定义工具、ApplyPatch 和流式输出，再修改 `docker-compose.yml` 中的镜像标签。不要直接使用 `latest`。

## 常用命令

```sh
docker compose ps
docker compose logs -f litellm
docker compose pull
docker compose up -d
docker compose down
```

删除数据库中的全部数据：

```sh
docker compose down -v
```

该命令不可恢复。

## 本地检查

无需安装项目依赖：

```sh
node --check web/site/app.js
node tests/check-static.mjs
docker compose config --quiet
docker build -t api2cursor-next-web ./web
```

## 许可证

[MIT](LICENSE)
