# LLM Gateway Lite

面向个人用户的轻量 Cursor 模型网关。直接运行 LiteLLM Proxy，不包含自建 Web、Nginx 或前端。

本地栈是三个容器：

- `litellm`：官方管理后台、OpenAI 兼容接口、Cursor `/cursor` 入口
- `db`：PostgreSQL，保存模型、凭据、Virtual Key、预算和用量
- `redis`：路由协调和 fallback

当前镜像基于 LiteLLM `v1.98.0-rc.1`。模型不写死在 `config.yaml` 里，而是后台入库（`store_model_in_db: true`）。`call_id_hook.py` 只做 Cursor / 上游兼容，不解析模型名后缀。

提供：

- LiteLLM 官方管理后台
- Cursor Ask、Plan、Agent
- OpenAI 兼容 `/v1/chat/completions`
- 模型与上游管理
- Virtual Key、预算、速率和用量记录
- 本地 Docker Compose 与雨云部署模板

## 快速开始

先复制环境变量模板，再填随机密钥。不要直接用 `scripts/init.*` 当完整初始化：它们目前只生成 Master Key、Salt Key、Postgres 密码和本地地址，缺少 Compose 必填的 `UI_PASSWORD` 和 `REDIS_PASSWORD`。

Windows PowerShell：

```powershell
Copy-Item .env.example .env
notepad .env
docker compose up -d --build
```

Linux 或 macOS：

```sh
cp .env.example .env
# 编辑 .env，填入随机密钥
docker compose up -d --build
```

启动后：

| 用途 | 地址 |
| --- | --- |
| 管理后台 | `http://localhost:3029/ui/` |
| 就绪检查 | `http://localhost:3029/health/readiness` |
| OpenAI 兼容接口 | `http://localhost:3029/v1/` |
| Cursor Base URL | `http://localhost:3029/cursor` |

后台登录：

```text
用户名：.env 中的 UI_USERNAME，默认 admin
密码：.env 中的 UI_PASSWORD
```

`LITELLM_MASTER_KEY` 是最高权限 API Key，不是后台密码，也不要填进 Cursor。

## 环境变量

以 `.env.example` 和 `docker-compose.yml` 为准：

| 变量 | 用途 |
| --- | --- |
| `LITELLM_MASTER_KEY` | 最高权限 API Key，必须以 `sk-` 开头 |
| `LITELLM_SALT_KEY` | 加密数据库里的上游凭据，添加模型后不要更换 |
| `UI_USERNAME` | 后台用户名，默认 `admin` |
| `UI_PASSWORD` | 后台密码 |
| `PROXY_ADMIN_ID` | 后台管理员 ID，默认 `admin` |
| `POSTGRES_PASSWORD` | PostgreSQL 密码 |
| `REDIS_PASSWORD` | Redis 密码 |
| `LITELLM_VERSION` | 构建 LiteLLM 基础镜像的版本，当前 `v1.98.0-rc.1` |
| `PUBLIC_BASE_URL` | 对外访问根地址，本地默认 `http://localhost:3029` |

安全要求：

- 不要把真实密钥提交到 Git
- Cursor 只使用 Virtual Key
- 不要把 Master Key、Salt Key、上游供应商 Key 配到 Cursor
- `LITELLM_SALT_KEY` 一旦用于加密模型凭据就不能更换
- 完整 Virtual Key 通常只显示一次，创建后立即保存

## 目录

```text
docker-compose.yml          本地三容器：LiteLLM + PostgreSQL + Redis
rainyun-compose.yml         雨云两容器模板：LiteLLM + PostgreSQL
.env.example                环境变量模板
litellm/Dockerfile          固定 LiteLLM 版本，并打入 config 与 hook
litellm/config.yaml         全局设置、Redis、fallback、hook 注册
litellm/call_id_hook.py     Cursor 消息与 Responses 兼容处理
scripts/init.ps1            仅生成部分密钥，不能单独当完整初始化
scripts/init.sh             同上
docs/configuration.md       雨云部署、备份升级、完整故障排查
tests/check-static.mjs      仓库静态契约检查
```

`config.yaml` 里的 `model_list` 是空的。模型、密钥、Virtual Key 都在后台写入 PostgreSQL。

## 后台加模型

进入 `Models + Endpoints`。关键字段：

| 字段 | 含义 |
| --- | --- |
| Public Model Name | 对 Cursor / 客户端公开的名字 |
| LiteLLM Model Name | LiteLLM 用来选供应商、协议和上游模型的内部名 |
| API Base | 上游 API 根地址，不要带 `/chat/completions` 或 `/responses` |
| API Key | 上游供应商密钥 |
| RPM / TPM | 该部署的速率限制，不确定时留空 |

同一个 Public Model Name 可以挂多个部署，由 LiteLLM 路由。

### Chat Completions 还是 Responses

部分上游公开了 `/v1/chat/completions`，但会拒绝这条路径，只接受 `/v1/responses`。典型报错：

```text
Your request was blocked
Available Model Group Fallbacks=None
```

这时不要只测 Playground 的 `/v1/responses`。Cursor 实际走 Chat Completions。对外仍用 Public Model Name，内部改成 Responses 桥接：

```text
Public Model Name：gpt-5.6-sol
LiteLLM Model Name：openai/responses/gpt-5.6-sol
API Base：https://api.orangecc.cc/v1
```

`openai/responses/` 的意思是：LiteLLM 接收 `/v1/chat/completions`，内部转成上游 `/v1/responses`，再把结果转回 Chat Completions。Cursor 里只填 Public Model Name，不要填带前缀的内部名。

验证必须用：

```text
Endpoint Type：/v1/chat/completions
```

普通 Chat Completions 上游不要盲目加这个前缀。

### 当前约定

这些名字是运行时后台配置，不是仓库硬编码。改上游后以后台为准。

| Public Model Name | 用途 | 内部模型名 |
| --- | --- | --- |
| `gpt-5.6-sol` | GPT 主线 | `openai/responses/gpt-5.6-sol` |
| `gpt-5.6-sol-pro` | GPT 兜底 | `openai/responses/gpt-5.6-sol-pro` |
| `grok-46-low` / `medium` / `high` / `xhigh` | Grok 思考档位 | `openai/responses/grok-4.6` |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | `anthropic/claude-sonnet-4-6` |
| `claude-opus-4-8` | Claude Opus 4.8 | `anthropic/claude-opus-4-8` |
| `claude-sonnet-5` | Claude Sonnet 5 | `anthropic/claude-sonnet-5` |
| `claude-opus-5` | Claude Opus 5 | `anthropic/claude-opus-5` |

Grok 用自定义名，是因为 Cursor 会拦截官方名，例如 `grok-4.6`。Claude 使用 OrangeCC 的 Anthropic 原生协议，LiteLLM 内部模型名是 `anthropic/...`，API Base 是 `https://api.orangecc.cc`；Cursor 仍使用表中的 Public Model Name。

`config.yaml` 里的 fallback：

```yaml
fallbacks:
  - gpt-5.6-sol:
      - gpt-5.6-sol-pro
```

主线 `gpt-5.6-sol` 失败时切到 `gpt-5.6-sol-pro`。两个部署都要存在，否则会报 `No deployments available for selected model`。

Grok 思考深度用独立 Public Model Name：`grok-46-low` / `grok-46-medium` / `grok-46-high` / `grok-46-xhigh`。Cursor 里直接填这些名字，不要加 `-thinking-*` 或 `[context=...]`。Cursor Settings 不会解析这类后缀。

## Virtual Key

1. 先在 Playground 用 `/v1/chat/completions` 测通模型
2. 进入 `Virtual Keys` → `Create New Key`
3. 设置 Alias
4. Models 选需要开放的 Public Model Name，或 `*` 表示全部当前和未来模型
5. 按需设置预算、RPM、TPM、过期时间
6. 创建后立刻保存完整 Key

Cursor 只用 Virtual Key。如果 Key 的模型列表不含目标 Public Model Name，会直接拒绝。`User API Key Rate limit exceeded` 通常是这把 Key 的 RPM/TPM 到了，不是上游挂了。

## Cursor 接入

Cursor Settings → Models：

1. 启用 OpenAI API Key，填 LiteLLM Virtual Key
2. 启用 Override OpenAI Base URL
3. Base URL 填 `https://你的域名/cursor`，本地是 `http://localhost:3029/cursor`
4. 添加 LiteLLM 的 Public Model Name

不要填：

```text
https://你的域名/cursor/v1
https://你的域名/v1
https://你的域名/cursor/chat/completions
openai/responses/gpt-5.6-sol
```

Cursor 会拦截和内置模型撞名的自定义名。官方 Grok 名容易被拦，所以用 `grok-46-*`；Claude 则尽量用 Cursor 已认识的名字。Grok 在 Cursor 中填写 `grok-46-high` 这类独立档位名。

## `call_id_hook.py` 做什么

它不是过滤器，也不会改 Request Logs 的展示。它是 LiteLLM 的 `CustomLogger` 预调用钩子，在请求进路由器之前改 payload。`config.yaml` 里这样注册：

```yaml
litellm_settings:
  drop_params: true
  callbacks: /app/call_id_hook.proxy_handler_instance
```

`drop_params: true` 会丢掉上游不认识的参数，避免多余字段把请求打挂。hook 不再解析 `-thinking-*` 或 `[context=...]`。

### 1. 补 Responses 的 `created_at`

部分上游（例如 OrangeCC）成功返回 Responses JSON，但没有 `created_at`。LiteLLM 会把它当成错误。hook 在解析响应时补 `created_at: 0`。

### 2. 截断过长 `tool_call_id`

部分上游限制 tool call id 最长 64。Cursor / Agent 有时会给出更长的 id。超出部分会截断并追加短 hash，避免上游直接拒请求。

### 3. 规范化 Cursor 的 user 消息

Cursor Agent 有时把 Anthropic 风格的 `tool_result` 放进 `role: user` 的 `content` 数组。LiteLLM 按 OpenAI Chat Completions 校验，会报：

```text
Invalid user message at index 0
```

hook 会把 `tool_result` 抽成 `role: tool`，并把其余文本收成普通 user 消息。

Claude 渠道现在不再使用 `openai/responses/claude-*`，而是使用：

```text
LiteLLM Model Name：anthropic/claude-*
API Base：https://api.orangecc.cc
```

这样 LiteLLM 会按 Anthropic 协议请求 OrangeCC 的 Claude 渠道，Request Logs 中应显示 `anthropic`。Grok 和 GPT 仍保留 `openai/responses/...`，因为它们使用 OrangeCC 的 OpenAI Responses 兼容入口。

这些处理只改即将发给 LiteLLM / 上游的请求，不删除日志，也不按 `call_type` 过滤后台页面。

## 日志

有三层，不要混：

| 位置 | 看到什么 |
| --- | --- |
| `docker compose logs -f litellm` | 进程、迁移、异常栈 |
| LiteLLM UI → Request Logs | 默认常按 Chat Completions 过滤 |
| PostgreSQL spend logs | 实际落库记录，包含 `call_type=responses` |

Grok 走 `openai/responses/` 时，日志的 `call_type` 经常是 `responses`；Claude 改成 Anthropic 后应按 `anthropic` 方向排查。Request Logs 默认视图可能看不到，但数据库里有。换过滤器或直接查库。

排查时保留 Request ID。不要把 API Key、Authorization Header 或完整凭据贴到公开地方。

## 常见问题

**`User API Key Rate limit exceeded`**
Virtual Key 的 RPM/TPM 到了。提高这把 Key 的限额，或换一把限额更高的 Key。

**Playground 的 `/v1/responses` 成功，Cursor 失败**
Cursor 走 `/v1/chat/completions`。内部模型名改成 `openai/responses/上游模型名`，再用 Chat Completions 测。

**`Invalid user message at index N`**
Cursor 发了非 OpenAI 形状的 user 消息。确认镜像已包含当前 `call_id_hook.py`，并已重建 LiteLLM 容器。

**Cursor 提示模型名无效，或 `already available as ...`**
自定义名和 Cursor 内置名冲突。Grok 用 `grok-46-*` 这类名字。

**自定义 Grok 显示 200k 上下文**
Cursor Settings 里的自定义模型名不会解析 `[context=...]`。直接用 `grok-46-high`。若聊天模型选择器有 Edit，再在那里改 Context。

**主线 GPT 500，fallback 也失败**
确认 `gpt-5.6-sol-pro` 还在，且协议、地址、密钥都可用。fallback 名字对不上等于没有兜底。

**Request Logs 只有 GPT，没有 Grok / Claude**
先看 `call_type`。Responses 桥接日志默认不一定出现在当前 UI 过滤器里。

**雨云 `Bad Gateway` / `no available server`**
容器 `4000` 没起来。先给 LiteLLM `2 vCPU`、`2048 MB`，检查密钥和数据库地址。细节见 `docs/configuration.md`。

## 项目检查

```sh
node tests/check-static.mjs
docker compose config --quiet
docker compose -f rainyun-compose.yml config --no-interpolate --quiet
docker build -t llm-gateway-lite ./litellm
```

## 更多文档

雨云导入、资源配额、备份升级、安全清单和更长的故障排查，见：

**[完整配置与故障排查](docs/configuration.md)**

本地 Compose 已经包含 Redis；雨云模板目前仍是 LiteLLM + PostgreSQL 两容器。雨云步骤以 `docs/configuration.md` 为准。

## 许可证

[MIT](LICENSE)
