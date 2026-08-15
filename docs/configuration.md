# LLM Gateway Lite 完整配置与故障排查

本文档覆盖本地部署、雨云部署、LiteLLM 后台、上游模型、Virtual Key、Cursor 接入、完整能力验证、备份升级和已知问题。

项目固定使用 LiteLLM Proxy `v1.97.0-rc.1` 与 PostgreSQL。除非已经完成兼容性回归测试，不要自行替换为 `latest`。

## 1. 架构、端口与资源

部署包含两个容器：

- `litellm`：LiteLLM Proxy、官方管理后台、OpenAI 兼容接口和 Cursor 接口
- `db`：PostgreSQL，保存模型、凭据、Virtual Key、预算和用量数据

对外入口：

| 用途 | 本地地址 | 公网地址 |
| --- | --- | --- |
| 管理后台 | `http://localhost:3029/ui/` | `https://你的域名/ui/` |
| 就绪检查 | `http://localhost:3029/health/readiness` | `https://你的域名/health/readiness` |
| OpenAI 兼容接口 | `http://localhost:3029/v1/` | `https://你的域名/v1/` |
| Cursor Base URL | `http://localhost:3029/cursor` | `https://你的域名/cursor` |

本地 Docker 空闲实测：

- LiteLLM：约 `740-761 MiB`
- PostgreSQL：约 `55-57 MiB`
- 合计：约 `795-818 MiB`

个人部署建议：

- 首次启动或迁移：LiteLLM `2 vCPU`、`2048 MB`
- 稳定低并发：LiteLLM `1 vCPU`、`1024 MB`
- PostgreSQL：`0.5 vCPU`、`256 MB`
- 项目可用内存：至少 `2 GB`
- LiteLLM 副本数：`1`
- Worker 数：`1`

`1024 MB` 只适合个人低并发。Agent 长任务、并行工具调用或数据库迁移期间出现 OOM 时，将 LiteLLM 提高到 `2048 MB`。

## 2. 密钥说明

部署需要三个互不相同的随机值：

| 变量 | 用途 | 要求 |
| --- | --- | --- |
| `LITELLM_MASTER_KEY` | 后台管理员密码和最高权限 API Key | 必须以 `sk-` 开头 |
| `LITELLM_SALT_KEY` | 加密数据库中的上游凭据 | 必须以 `sk-` 开头，添加模型后不可更换 |
| `POSTGRES_PASSWORD` | PostgreSQL 用户密码 | 使用长随机值 |

安全要求：

- 不要把真实密钥提交到 Git
- 不要把 Master Key 配置到 Cursor
- Cursor 只使用受限的 Virtual Key
- `LITELLM_SALT_KEY` 一旦用于加密模型凭据就不能更换
- 完整 Virtual Key 通常只显示一次，创建后立即保存
- 任何曾出现在聊天、截图、日志或公开仓库中的密钥都应立即撤销并重新生成

## 3. 本地部署

### 3.1 前置条件

安装 Docker Desktop 或 Docker Engine，并确认 Docker Compose 可用。

### 3.2 生成 `.env`

Windows PowerShell：

```powershell
.\scripts\init.ps1
```

Linux 或 macOS：

```sh
chmod +x ./scripts/init.sh
./scripts/init.sh
```

脚本会生成：

```text
LITELLM_MASTER_KEY=sk-随机值
LITELLM_SALT_KEY=sk-随机值
POSTGRES_PASSWORD=随机值
PUBLIC_BASE_URL=http://localhost:3029
```

如果 `.env` 已存在，脚本不会覆盖。

### 3.3 启动

```sh
docker compose up -d --build
docker compose ps
```

查看日志：

```sh
docker compose logs -f litellm
docker compose logs -f db
```

访问 `http://localhost:3029/health/readiness`。返回成功后打开 `http://localhost:3029/ui/`。

后台登录信息：

```text
用户名：admin
密码：.env 中的 LITELLM_MASTER_KEY
```

### 3.4 停止与清理

停止容器并保留数据：

```sh
docker compose down
```

删除容器和全部本地数据库数据：

```sh
docker compose down -v
```

`docker compose down -v` 不可恢复，不要把它当作普通重启命令。

## 4. 雨云部署

雨云云应用 RCA 支持多容器和 Docker Compose 导入。控制台名称可能随版本变化；本文中的“应用模板”“版本编辑”和“从 Docker 导入”以当前控制台对应入口为准。

### 4.1 生成三个密钥

Windows PowerShell 5.1 及以上：

```powershell
function New-RandomSecret {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
}

$master = "sk-$(New-RandomSecret)"
$salt = "sk-$(New-RandomSecret)"
$postgres = New-RandomSecret
$master
$salt
$postgres
```

分别保存为 `LITELLM_MASTER_KEY`、`LITELLM_SALT_KEY` 和 `POSTGRES_PASSWORD`。

### 4.2 导入 Compose

1. 登录雨云控制台并进入“云应用”。
2. 创建项目，确保至少还有 `2 GB` 可分配内存。
3. 创建个人应用模板和新版本。
4. 选择“从 Docker 导入”。
5. 导入仓库根目录的 `rainyun-compose.yml`。
6. 确认出现 `litellm` 和 `db` 两个容器。

`rainyun-compose.yml` 使用可直接解析的占位值。不要在导入前把普通变量改成嵌套 `${VAR}`；雨云导入器只应保留平台生成的 `${rca_svc_*}` 引用。

`litellm` 服务设置了 `pull_policy: always`。雨云保留该字段时，每次重新部署都会检查并拉取项目 `latest` 镜像。该设置不会定时重建应用，也不会自动更新 `litellm/Dockerfile` 中固定的 LiteLLM 基础版本；升级仍需先修改固定版本、通过 CI 发布新镜像，再在雨云重新部署。

### 4.3 配置 `litellm` 容器

资源：

```text
首次启动 CPU：2000m
首次启动内存：2048 MB
稳定后可尝试 CPU：1000m
稳定后可尝试内存：1024 MB
```

环境变量：

```text
DATABASE_URL=postgresql://litellm:数据库密码@${rca_svc_db_postgres}/litellm
LITELLM_MASTER_KEY=sk-你的MasterKey
LITELLM_SALT_KEY=sk-你的SaltKey
STORE_MODEL_IN_DB=True
```

要求：

- `DATABASE_URL` 只替换密码部分
- 必须保留 `${rca_svc_db_postgres}`
- Command 和 Args 保持为空
- 镜像自带启动参数为 `--config /app/config.yaml --port 4000 --num_workers 1`

外部服务：

```text
服务名称：api
显示名称：LiteLLM
服务类型：外部访问
内部端口：4000
协议：TCP
```

### 4.4 配置 `db` 容器

资源：

```text
CPU：500m
内存：256 MB
```

环境变量：

```text
POSTGRES_DB=litellm
POSTGRES_USER=litellm
POSTGRES_PASSWORD=与 DATABASE_URL 完全相同的数据库密码
```

内部服务：

```text
服务名称：postgres
显示名称：PostgreSQL
服务类型：内部访问
内部端口：5432
协议：TCP
```

`${rca_svc_db_postgres}` 依赖容器名 `db` 和服务名 `postgres`，不要修改这两个名称。

### 4.5 配置数据库持久化

确认 `db` 容器存在：

```text
名称：postgres-data
挂载路径：/var/lib/postgresql/data
子路径：llm-gateway-lite/postgres
内容类型：目录
```

没有持久化挂载时，容器重建会丢失模型、上游凭据、Virtual Key、预算和用量记录。

### 4.6 安装与 HTTPS

1. 确认页面中不存在任何 `replace-with-` 占位值。
2. 保存模板版本并安装应用。
3. 等待 PostgreSQL 初始化和 LiteLLM 数据库迁移完成。
4. 在网站管理中添加“应用代理”网站。
5. 选择 `litellm` 容器的 `api` 服务。
6. 使用雨云域名或自定义域名。
7. 启用 HTTPS。

普通后台和 Cursor 接入不要求设置 `PROXY_BASE_URL`。只有使用 SSO 或 MCP OAuth 等需要生成外部回调地址的能力时，才添加：

```text
PROXY_BASE_URL=https://你的域名
```

该值只包含协议和域名，不带尾斜杠或路径。

按顺序检查：

```text
https://你的域名/health/liveliness
https://你的域名/health/readiness
https://你的域名/ui/
https://你的域名/cursor
```

访问 `/cursor` 返回 `307` 并跳转到 `/cursor/` 属于正常行为。直接访问 `/cursor/` 且没有 API Key 时返回 `401`，说明路由存在且鉴权生效。

## 5. LiteLLM 后台配置

### 5.1 登录

打开 `https://你的域名/ui/`：

```text
用户名：admin
密码：LITELLM_MASTER_KEY
```

### 5.2 添加普通 OpenAI 官方模型

进入 `Models + Endpoints` → `Add Model`：

```text
Provider：OpenAI
Public Model Name：gpt-4.1
LiteLLM Model Name：openai/gpt-4.1
API Key：OpenAI API Key
API Base：留空
```

### 5.3 添加普通 OpenAI 兼容上游

```text
Provider：OpenAI 或 OpenAI Compatible
Public Model Name：my-model
LiteLLM Model Name：openai/上游实际模型名
API Key：上游 API Key
API Base：https://上游地址/v1
```

`API Base` 填写 API 根地址，不要填写具体的 `/chat/completions` 或 `/responses` 路径。

### 5.4 添加 Anthropic 官方模型

```text
Provider：Anthropic
Public Model Name：claude-sonnet
LiteLLM Model Name：anthropic/上游实际模型名
API Key：Anthropic API Key
API Base：留空
```

Azure OpenAI 必须选择 Azure Provider，并按 Azure 的部署名、Endpoint 和 API Version 配置，不能套用普通 OpenAI 兼容示例。

### 5.5 字段含义

- `Public Model Name`：LiteLLM 对客户端公开的名称，也是 Cursor 中添加的模型名称
- `LiteLLM Model Name`：LiteLLM 用于选择供应商、协议和上游模型的内部名称
- `API Base`：上游 API 根地址
- `API Key`：上游供应商密钥，由 LiteLLM 使用 Salt Key 加密后保存
- `RPM`、`TPM`：上游部署的请求和 Token 限制，不确定时留空

同一个 Public Model Name 可以配置多个部署，由 LiteLLM 路由。上游实际模型名应从供应商文档或 `/v1/models` 获取，不要根据展示名称猜测。

## 6. Responses-only 上游配置

部分 OpenAI 兼容上游虽然公开 `/v1/chat/completions`，但会拒绝该路径，只允许 `/v1/responses`。典型表现：

```text
Provider returned error:
litellm.APIError: APIError: OpenAIException - Your request was blocked.
Received Model Group=模型名
Available Model Group Fallbacks=None
code=403
```

先分别测试上游：

- `/v1/chat/completions` 返回 `403 Your request was blocked`
- `/v1/responses` 正常返回

这种情况下，不能只因为 Playground 的 `/v1/responses` 测试成功就认为 Cursor 可用。Cursor 请求仍可能进入 Chat Completions 路径。

应保留对外模型名，并把内部模型名改为 Responses 桥接形式：

```text
Public Model Name：gpt-5.6-sol
LiteLLM Model Name：openai/responses/gpt-5.6-sol
API Base：https://xfpa.orangecc.cc/v1
Provider：OpenAI
```

LiteLLM Params 中的 `model` 也应为：

```text
openai/responses/gpt-5.6-sol
```

`openai/responses/` 会让 LiteLLM 接受 `/v1/chat/completions` 请求，在内部调用上游 Responses API，再返回标准 Chat Completions 形状。Cursor 中仍填写 Public Model Name `gpt-5.6-sol`，不能填写带前缀的内部名称。

修改后必须在 Playground 中选择：

```text
Endpoint Type：/v1/chat/completions
Model：gpt-5.6-sol
```

只有该测试成功，才证明 Cursor 所需路径已经桥接成功。

不要对所有模型盲目使用 `openai/responses/`。普通 Chat Completions-only 上游应保持普通 OpenAI 兼容配置；Responses-only 或明确需要 Responses 能力的模型才使用该前缀。

## 7. 创建 Virtual Key

1. 在 Playground 完成 `/v1/chat/completions` 测试。
2. 进入 `Virtual Keys`。
3. 选择 `Create New Key`。
4. 设置便于识别的 Alias。
5. Models 只选择需要开放的 Public Model Name。
6. 按需设置预算、RPM、TPM 和过期时间。
7. 创建后立即保存完整 Key。

Cursor 应使用 Virtual Key，不应使用：

- 上游供应商 API Key
- `LITELLM_MASTER_KEY`
- `LITELLM_SALT_KEY`

如果 Key 的 Models 列表不包含目标 Public Model Name，请求会因模型访问限制失败。

## 8. Cursor 配置

在 Cursor 的 Models 设置中：

1. 启用 OpenAI API Key。
2. 填写 LiteLLM 创建的 Virtual Key。
3. 启用 `Override OpenAI Base URL`。
4. Base URL 填写 `https://你的域名/cursor`。
5. 添加 LiteLLM 的 Public Model Name。
6. 选择该模型开始测试。

示例：

```text
Base URL：https://你的域名/cursor
API Key：LiteLLM Virtual Key
Model：gpt-5.6-sol
```

不要填写：

```text
https://你的域名/cursor/v1
https://你的域名/v1
https://你的域名/cursor/chat/completions
openai/responses/gpt-5.6-sol
```

本项目的 Cursor 入口是 `/cursor`，模型名是 Public Model Name。

## 9. 完整能力验证

普通文本成功只证明基础生成可用，不能证明 Agent 工具链完整可用。

### 9.1 后台验证

在 LiteLLM Playground 中：

1. 选择 `/v1/chat/completions`。
2. 选择目标 Public Model Name。
3. 发送普通消息。
4. 确认非流式或流式返回正常。
5. 确认没有 `403`、模型不存在或参数错误。

### 9.2 Cursor 分级验证

按顺序测试：

1. Ask：普通多轮文本对话
2. Plan：读取仓库并生成计划
3. Agent：读取文件和搜索代码
4. Agent：执行终端命令
5. Agent：创建临时文件
6. Agent：读取并修改临时文件
7. Agent：删除临时文件
8. Agent：连续调用多个工具
9. Agent：工具结果返回后继续推理
10. Agent：确认 Git 工作区无测试残留

当前已验证的 `gpt-5.6-sol` 链路：

```text
Cursor
→ LiteLLM /cursor
→ /v1/chat/completions
→ openai/responses/gpt-5.6-sol 桥接
→ 上游 /v1/responses
```

已实际通过：

- 多轮对话
- Web 搜索
- 文件枚举
- 代码搜索
- 文件读取
- 文件创建
- 文件修改
- 文件删除
- PowerShell 和 Python 终端命令
- Git 状态检查
- 多工具并行调用
- 工具结果回传后的继续推理

这不自动保证所有高级能力。图片理解、超长上下文、MCP、复杂工具参数、工具失败自动恢复和长时间 Agent 任务仍需按实际模型与使用场景专项验证。

## 10. 备份与升级

必须一起备份：

- PostgreSQL 持久化卷
- `LITELLM_SALT_KEY`
- `LITELLM_MASTER_KEY`
- `POSTGRES_PASSWORD`

只备份数据库但丢失 Salt Key，已加密的上游 API Key 无法恢复。

升级流程：

1. 备份数据库卷和三个密钥。
2. 在测试环境修改 `litellm/Dockerfile` 的固定版本。
3. 重新构建镜像。
4. 验证数据库迁移。
5. 验证后台登录、模型读取和上游凭据解密。
6. 验证 Virtual Key 权限。
7. 验证 Ask、Plan、Agent、工具调用、文件编辑和流式输出。
8. 验证后再更新生产环境。

不要直接把镜像改成 `latest`。LiteLLM 的 `/cursor`、Responses 桥接、参数转换和 Admin UI 行为都可能随版本变化。

## 11. 已知问题与排查

### 11.1 雨云返回 `Bad Gateway` 或 `no available server`

含义：HTTPS 网站已建立，但容器 `4000` 端口后没有可用的 LiteLLM 进程。

处理：

1. 首次启动给 LiteLLM `2 vCPU`、`2048 MB`。
2. 保持 Command 和 Args 为空。
3. 检查三个占位密钥是否全部替换。
4. 检查 `DATABASE_URL` 是否保留 `${rca_svc_db_postgres}`。
5. 检查数据库密码与 `POSTGRES_PASSWORD` 是否完全一致。
6. 检查 `db` 容器名、`postgres` 服务名和 `5432` 端口。
7. 查看 LiteLLM 日志中的 Prisma migration 错误。
8. 先检查 `/health/liveliness`，再检查 `/health/readiness`。

如果 LiteLLM 完全没有日志，优先检查容器命令是否被雨云表单覆盖，以及内存是否不足以启动。

### 11.2 PostgreSQL 出现 locale 或 `trust` 警告

`postgres:16-alpine` 使用 musl，可能出现：

```text
locale: not found
no usable system locales were found
```

初始化期间也可能看到本地 Unix Socket 使用 `trust` 的提示。只要日志最终出现：

```text
database system is ready to accept connections
```

数据库即已就绪。初始化过程中临时启动、关闭并再次正式启动属于正常流程。

### 11.3 LiteLLM 一直重启

检查：

- `DATABASE_URL` 是否正确
- `${rca_svc_db_postgres}` 是否保留
- 数据库密码是否一致
- `LITELLM_MASTER_KEY` 和 `LITELLM_SALT_KEY` 是否非空且以 `sk-` 开头
- PostgreSQL 是否已就绪
- Prisma migration 是否失败
- 内存是否发生 OOM

### 11.4 后台无法登录

```text
用户名：admin
密码：LITELLM_MASTER_KEY
```

修改 Master Key 后重启 LiteLLM。不要使用 Virtual Key 登录管理后台。

### 11.5 添加模型后调用失败

按顺序检查：

1. API Base 是否为正确的 API 根地址
2. LiteLLM Model Name 是否包含正确供应商前缀
3. 上游实际模型名是否存在
4. 上游 API Key 是否有效
5. 上游支持 Chat Completions 还是 Responses
6. Playground 的目标 Endpoint Type 是否与 Cursor 路径一致
7. Virtual Key 是否允许该 Public Model Name

先在后台 Playground 测试，再测试 Cursor。

### 11.6 Cursor 返回 `403 Your request was blocked`

如果 LiteLLM 错误中同时出现：

```text
OpenAIException - Your request was blocked
Received Model Group=...
Available Model Group Fallbacks=None
```

这通常不是 Cursor 本地权限问题，而是上游拒绝 LiteLLM 发出的 Chat Completions 请求。

确认上游 `/v1/responses` 可用而 `/v1/chat/completions` 被拒绝后，将 LiteLLM Model Name 改为：

```text
openai/responses/上游实际模型名
```

Public Model Name 保持不变，然后在 Playground 使用 `/v1/chat/completions` 重新测试。

### 11.7 Playground 的 Responses 测试成功，但 Cursor 失败

原因：Playground 直接测试 `/v1/responses` 没有覆盖 Cursor 的 Chat Completions 入口。

解决：在 Playground 中明确选择 `/v1/chat/completions`。Responses-only 上游使用 `openai/responses/` 内部模型名。

### 11.8 普通对话成功，但 Agent 工具失败

普通对话不会覆盖：

- Tool schema 转换
- Tool call 流式事件
- 多轮 Tool result
- 并行工具调用
- 文件编辑
- 终端调用

执行第 9 节完整能力验证。若失败，在 LiteLLM Logs 中根据 Request ID 检查请求参数和上游错误。

### 11.9 `Available Model Group Fallbacks=None`

这表示目标 Model Group 没有配置可用回退，不是原始故障本身。真正原因通常位于同一错误中的上游状态码和消息。

个人单上游部署可以不配置 fallback；需要高可用时，应给同一个 Public Model Name 添加多个可用部署或显式配置 fallback，并分别验证协议兼容性。

### 11.10 Cursor Base URL 配错

本项目使用：

```text
https://你的域名/cursor
```

不要自行追加 `/v1` 或具体接口路径。访问 `/cursor` 的 `307` 跳转和未鉴权 `/cursor/` 的 `401` 均属于正常现象。

### 11.11 Virtual Key 无权访问模型

检查 Virtual Key 的 Models 列表是否包含目标 Public Model Name。Cursor 使用的是 Public Model Name，不是 LiteLLM Model Name。

### 11.12 重建后数据丢失

检查 `db` 是否持久化挂载：

```text
/var/lib/postgresql/data
```

不要删除 Docker Volume 或雨云共享磁盘中的对应子路径。

### 11.13 更换 Salt Key 后上游凭据失效

Salt Key 用于加密数据库中的上游凭据。恢复原 Salt Key，或重新录入所有上游 API Key。无法通过新 Salt Key 解密旧数据。

### 11.14 内存不足或频繁重启

处理：

- LiteLLM 提高到 `1536-2048 MB`
- 项目总内存保持至少 `2 GB`
- 保持 `--num_workers 1`
- 个人部署只运行一个 LiteLLM 副本
- 首次迁移完成后再尝试降低资源

### 11.15 雨云 Compose 导入提示缺失环境变量

雨云导入阶段不能解析任意嵌套 `${VAR}`。使用仓库提供的 `rainyun-compose.yml`，只保留平台要求的 `${rca_svc_db_postgres}`，其余密钥先使用占位值并在导入界面替换。

### 11.16 GHCR 镜像拉取失败

确认：

- 镜像名为 `ghcr.io/ninthless/llm-gateway-lite:latest`
- GitHub Packages 对该镜像允许公开匿名拉取
- 雨云节点可以访问 GHCR
- 镜像构建工作流已经成功发布对应架构

### 11.17 修改模型后配置没有更新

进入模型详情确认：

- 顶部 `LiteLLM Model` 已显示新值
- `LiteLLM Params` 中的 `model` 已显示新值
- 页面出现保存成功提示

然后回到 Playground 重新选择模型。必要时刷新模型列表。

### 11.18 日志中的 Request ID

Cursor 报错时保留完整错误和 Request ID。使用 LiteLLM `Logs` 按时间、模型和状态码定位对应请求。排查时不要公开 API Key、Authorization Header 或完整凭据。

## 12. 安全清单

- 只公开 LiteLLM `4000` 服务
- PostgreSQL 仅内部访问
- 公网入口启用 HTTPS
- Cursor 只使用受限 Virtual Key
- Virtual Key 设置模型范围、预算和限速
- Master Key 和 Salt Key 不进入 Cursor
- `.env` 不提交到 Git
- Salt Key 不随意轮换
- 定期备份数据库卷与三个密钥
- 上游或 Virtual Key 一旦泄露立即撤销
- 升级前在测试环境验证完整 Agent 工具链

## 13. 项目检查命令

```sh
node tests/check-static.mjs
docker compose config --quiet
docker compose -f rainyun-compose.yml config --no-interpolate --quiet
docker build -t llm-gateway-lite ./litellm
```

运行状态：

```sh
docker compose ps
docker compose logs -f litellm
docker compose logs -f db
```

## 14. 资料来源

- [LiteLLM Docker Quickstart](https://docs.litellm.ai/docs/proxy/docker_quick_start)
- [LiteLLM Admin UI](https://docs.litellm.ai/docs/proxy/ui)
- [LiteLLM Model Management](https://docs.litellm.ai/docs/proxy/model_management)
- [LiteLLM Model Access](https://docs.litellm.ai/docs/proxy/model_access)
- [LiteLLM Responses API](https://docs.litellm.ai/docs/response_api)
- [LiteLLM OpenAI Provider](https://docs.litellm.ai/docs/providers/openai)
- [LiteLLM OpenAI Responses API](https://docs.litellm.ai/docs/providers/openai/responses_api)
- [LiteLLM Cursor Integration](https://docs.litellm.ai/docs/tutorials/cursor_integration)
- [LiteLLM Production Deployment](https://docs.litellm.ai/docs/proxy/deploy)
- [LiteLLM Production Best Practices](https://docs.litellm.ai/docs/proxy/prod)
- [雨云云应用 Docker Compose 更新公告](https://forum.rainyun.com/t/topic/12843)
- [雨云 App 版本制作教程](https://forum.rainyun.com/t/topic/11296)
- [雨云云应用快速上手](https://www.rainyun.com/docs/products/rca/start.html)
- [雨云应用管理](https://www.rainyun.com/docs/products/rca/project/apps.html)
