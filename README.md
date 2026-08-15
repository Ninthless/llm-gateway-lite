# API2Cursor Next

面向个人用户的轻量 Cursor 模型网关。项目直接运行 LiteLLM Proxy 和 PostgreSQL，不包含自建 Web、Nginx 或前端依赖。

保留 LiteLLM 原版能力：

- `/ui/` 官方管理后台
- `/cursor` Cursor Ask、Plan 和 Agent 接口
- `/v1/` OpenAI 兼容接口
- 模型与上游管理
- Virtual Key、预算、速率和用量记录

## 架构与资源

部署只包含两个容器：

- `litellm`：LiteLLM Proxy、官方管理后台和 Cursor 接口
- `db`：PostgreSQL，持久化模型、密钥、预算和用量数据

本机 Docker 空闲实测：

- LiteLLM：约 `740-761 MiB`
- PostgreSQL：约 `55-57 MiB`
- 合计：约 `795-818 MiB`

雨云建议限制：

- LiteLLM：`1 vCPU`、`1024 MB`
- PostgreSQL：`0.5 vCPU`、`256 MB`
- 项目可用内存：建议至少 `2 GB`

上述数值是雨云当前界面可选档位中的最低建议，不会由 Compose 导入器自动带入，必须在导入后手动设置。LiteLLM 空闲实测约 `740-761 MiB`，`1024 MB` 仅适合个人低并发；出现 OOM 或 Agent 长任务重启时，将 LiteLLM 提高到 `2048 MB`。项目总内存建议至少 `2 GB`，个人部署不需要 Redis；只有以后扩展多个 LiteLLM 实例时才需要重新设计共享限流和缓存。

## 本地运行

需要 Docker Desktop 或 Docker Engine，并启用 Docker Compose。

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

启动后访问：

- 官方管理后台：`http://localhost:3029/ui/`
- 健康检查：`http://localhost:3029/health/readiness`
- Cursor Base URL：`http://localhost:3029/cursor`

官方后台用户名为 `admin`，密码是 `.env` 中的 `LITELLM_MASTER_KEY`。

## 雨云个人部署教程

雨云云应用 RCA 已支持多容器和 Docker Compose 导入。雨云旧版百科仍可能显示“正在支持”，但 2025 年 12 月更新公告已明确该能力上线；如果控制台名称变化，以当前“应用模板”“版本编辑”和“从 Docker 导入”入口为准。

### 1. 准备三个密钥

在本机生成三个互不相同的随机值。Windows PowerShell 5.1 及以上版本可使用：

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

分别保存为：

- `LITELLM_MASTER_KEY`：官方后台管理员密码，必须以 `sk-` 开头
- `LITELLM_SALT_KEY`：数据库凭据加密密钥，必须以 `sk-` 开头
- `POSTGRES_PASSWORD`：PostgreSQL 密码

`LITELLM_SALT_KEY` 在添加模型后不能更换。更换后，数据库里已经加密的上游 API Key 将无法解密。

### 2. 创建雨云项目和应用模板

1. 登录雨云控制台，进入“云应用”。
2. 创建一个项目，建议保证项目至少还有 `2 GB` 可分配内存。
3. 进入“应用模板”，创建个人模板。
4. 新建一个版本，选择“从 Docker 导入”。
5. 导入仓库根目录的 [`rainyun-compose.yml`](rainyun-compose.yml)。

导入文件中的自定义环境变量使用可直接解析的占位值，避免雨云在选项创建前报“缺失对应的环境变量”。导入后应出现 `litellm` 和 `db` 两个容器。如果 `ghcr.io/ninthless/api2cursor-next-litellm:latest` 拉取失败，先确认 GitHub Packages 中该镜像允许公开匿名拉取。

### 3. 导入后必须修改的地方

Compose 可以直接通过雨云导入，但不能安全地零修改安装，因为管理员密钥、加密密钥和数据库密码必须由每位用户单独生成。导入完成后，先不要保存或安装，按下面顺序修改。

`litellm` 容器：

1. 打开顶部的 `litellm` 容器标签。
2. 在容器基本信息中，把“最小 CPU”改为 `1000m`。
3. 把“最小内存”改为 `1024 MB`。
4. 打开“环境变量”标签。
5. 将 `LITELLM_MASTER_KEY` 的值改成第 1 步生成的 `$master`。
6. 将 `LITELLM_SALT_KEY` 的值改成第 1 步生成的 `$salt`。
7. 找到 `DATABASE_URL`，只把其中的 `replace-with-random-postgres-password` 替换成第 1 步生成的 `$postgres`，保留 `${rca_svc_db_postgres}` 不变。
8. 确认 `STORE_MODEL_IN_DB` 的值是 `True`。
9. 打开“服务配置”标签，确认存在一项服务：

```text
服务名称：api
显示名称：LiteLLM
服务类型：外部访问
内部端口：4000
协议：TCP
```

`db` 容器：

1. 打开顶部的 `db` 容器标签。
2. 保持“最小 CPU”为平台最低档 `500m`。
3. 保持“最小内存”为平台最低档 `256 MB`。
4. 打开“环境变量”标签。
5. 将 `POSTGRES_PASSWORD` 的值改成同一个 `$postgres`。
6. 确认 `POSTGRES_DB` 和 `POSTGRES_USER` 都是 `litellm`。
7. 打开“服务配置”标签，确认存在一项服务：

```text
服务名称：postgres
显示名称：PostgreSQL
服务类型：内部访问
内部端口：5432
协议：TCP
```

8. 打开“持久化卷”标签，确认存在目录挂载：

```text
挂载路径：/var/lib/postgresql/data
内容类型：目录
```

修改完成后，`litellm` 的环境变量应类似：

```text
DATABASE_URL=postgresql://litellm:你生成的数据库密码@${rca_svc_db_postgres}/litellm
LITELLM_MASTER_KEY=sk-你生成的MasterKey
LITELLM_SALT_KEY=sk-你生成的SaltKey
STORE_MODEL_IN_DB=True
```

`db` 的环境变量应类似：

```text
POSTGRES_DB=litellm
POSTGRES_USER=litellm
POSTGRES_PASSWORD=你生成的同一个数据库密码
```

`${rca_svc_db_postgres}` 由雨云自动生成，依赖容器名 `db` 和服务名 `postgres`，不要修改。数据库密码在 `DATABASE_URL` 和 `POSTGRES_PASSWORD` 中必须完全一致。确认页面中不再出现任何 `replace-with-` 占位值后，才保存并安装。

### 4. 配置数据库持久化

如果 Compose 导入后没有自动生成持久化卷，在 `db` 容器的“持久化卷”标签中手动添加：

```text
名称：postgres-data
挂载路径：/var/lib/postgresql/data
子路径：api2cursor-next/postgres
内容类型：目录
```

没有这个挂载，容器重建后模型、Virtual Key 和用量数据会丢失。

### 5. 安装并绑定 HTTPS

1. 保存模板版本并安装应用。
2. 等待两个容器都进入运行状态，首次启动通常需要执行数据库迁移。
3. 在应用“服务”中确认 `litellm` 的 `4000` 服务可访问。
4. 在项目“网站管理”中添加“应用代理”网站。
5. 选择 `litellm` 容器的 `api` 服务。
6. 使用雨云分配域名或绑定自己的域名，并启用 HTTPS。
7. 普通管理后台和 Cursor 接入不要求 `PROXY_BASE_URL`。如果以后使用 SSO 或 MCP OAuth，再到 `litellm` 的“环境变量”中添加 `PROXY_BASE_URL=https://你的域名`，只能填写协议和域名，不能带尾斜杠或路径。

最终应能访问：

```text
https://你的域名/ui/
https://你的域名/health/readiness
https://你的域名/cursor
```

健康检查返回成功后再进行后台配置。`/cursor` 会以 `307` 跳转到 `/cursor/`；直接访问 `/cursor/` 且未携带 API Key 时返回 `401` 是正常的，说明路由存在且鉴权生效。

### 6. 配置 LiteLLM 官方后台

1. 打开 `https://你的域名/ui/`。
2. 用户名填写 `admin`。
3. 密码填写 `LITELLM_MASTER_KEY`。
4. 进入 Models，添加上游供应商、模型名称、API Base 和上游 API Key。
5. 设置一个供 Cursor 选择的 Public Model Name。
6. 进入 Virtual Keys，创建一个个人 Key。
7. 只给该 Key 开放需要的模型，并按需设置预算、RPM 和 TPM。
8. 保存完整 Virtual Key。完整值通常只在创建时显示一次。

不要在 Cursor 中直接使用 Master Key。Master Key 拥有管理权限，日常调用应使用 Virtual Key。

### 7. 配置 Cursor

在 Cursor 的 Models 设置中：

1. 启用 `Override OpenAI Base URL`。
2. Base URL 填写 `https://你的域名/cursor`。
3. API Key 填写第 6 步创建的 Virtual Key。
4. 模型名称填写 LiteLLM 中设置的 Public Model Name。

按顺序验证：

1. Ask 模式发送普通文本。
2. Plan 模式生成一个修改计划。
3. Agent 模式读取文件并调用工具。
4. 验证 ApplyPatch、自定义工具和流式输出。

文本可用不等于 Agent 完整可用，必须实际验证工具调用。

### 8. 备份与升级

必须一起保存：

- PostgreSQL 持久化卷
- `LITELLM_SALT_KEY`
- `LITELLM_MASTER_KEY`
- `POSTGRES_PASSWORD`

当前 LiteLLM 基础镜像精确固定为 `v1.97.0-rc.1`，用于获得 `/cursor` Agent 支持。不要在雨云中直接改成 LiteLLM `latest`。

升级流程：

1. 备份数据库卷和三个密钥。
2. 在测试环境修改 [`litellm/Dockerfile`](litellm/Dockerfile) 的版本。
3. 重新构建镜像。
4. 验证后台登录、模型读取和 Virtual Key。
5. 验证 Ask、Plan、Agent、工具调用、ApplyPatch 和流式输出。
6. 通过后再更新雨云应用。

### 9. 常见问题

`litellm` 一直重启：

- 检查 `DATABASE_URL` 是否使用 `${rca_svc_db_postgres}`
- 检查容器名是否为 `db`、数据库服务名是否为 `postgres`
- 检查三个密钥是否为空
- 查看 LiteLLM 日志中的 Prisma migration 错误

官方后台无法登录：

- 用户名必须是 `admin`
- 密码是 `LITELLM_MASTER_KEY`
- 修改 Master Key 后必须重启 LiteLLM

添加模型后调用失败：

- 检查上游 API Base 是否包含正确路径
- 检查 LiteLLM 供应商前缀和上游模型名
- 检查上游 API Key 是否有效
- 先在官方后台 Playground 测试，再测试 Cursor

重建后数据丢失：

- 检查 `db` 是否挂载 `/var/lib/postgresql/data`
- 不要删除雨云项目共享磁盘中的对应子路径

内存不足或频繁重启：

- 将 LiteLLM 提高到 `1536 MB`
- 项目总内存保持至少 `2 GB`
- 保持 `--num_workers 1`
- 个人部署不要启动多个 LiteLLM 副本

## 安全

- 只公开 LiteLLM `4000` 服务，不公开 PostgreSQL
- 公网访问必须使用 HTTPS
- 不要提交 `.env` 或任何真实密钥
- 不要把 Master Key 配置到 Cursor
- Salt Key 一经使用不要更换
- 定期备份数据库卷和密钥
- 给 Virtual Key 设置模型范围和预算

## 常用命令

```sh
docker compose ps
docker compose logs -f litellm
docker compose up -d --build
docker compose down
```

删除本地数据库中的全部数据：

```sh
docker compose down -v
```

该命令不可恢复。

## 本地检查

```sh
node tests/check-static.mjs
docker compose config --quiet
docker compose -f rainyun-compose.yml config --no-interpolate --quiet
docker build -t api2cursor-next-litellm ./litellm
```

## 资料来源

- [LiteLLM Docker Quickstart](https://docs.litellm.ai/docs/proxy/docker_quick_start)
- [LiteLLM Production Deployment](https://docs.litellm.ai/docs/proxy/deploy)
- [LiteLLM Production Best Practices](https://docs.litellm.ai/docs/proxy/prod)
- [雨云云应用 Docker Compose 更新公告](https://forum.rainyun.com/t/topic/12843)
- [雨云 App 版本制作教程](https://forum.rainyun.com/t/topic/11296)
- [雨云云应用快速上手](https://www.rainyun.com/docs/products/rca/start.html)
- [雨云应用管理](https://www.rainyun.com/docs/products/rca/project/apps.html)

## 许可证

[MIT](LICENSE)
