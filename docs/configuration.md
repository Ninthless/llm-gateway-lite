# LLM Gateway Lite Configuration and Troubleshooting

**English** | [简体中文](configuration.zh-CN.md) | [日本語](configuration.ja.md)

This document matches the current production environment and covers Rainyun RCA cloud-app deploy, cloud ops, local Docker testing, LiteLLM admin UI, upstream models, Virtual Keys, Cursor setup, full capability verification, backup/upgrade, and known issues.

The current production deployment uses Rainyun RCA cloud apps. The LiteLLM image is provided by GitHub Container Registry, and the database is PostgreSQL. The image pins LiteLLM Proxy `v1.98.0-rc.1`. To upgrade, first change the pinned version in `litellm/Dockerfile`, publish through CI, then deploy.

## 1. Architecture, Ports, and Resources

Local Docker Compose includes three containers:

- `litellm`: LiteLLM Proxy, official admin UI, OpenAI-compatible API, and Cursor endpoint
- `db`: PostgreSQL, stores models, credentials, Virtual Keys, budgets, and usage data
- `redis`: route coordination, rate-limit state, and cache

The production Rainyun RCA template includes two containers:

- `litellm`: pulled from `ghcr.io/ninthless/llm-gateway-lite:latest`
- `db`: PostgreSQL, connected through the RCA internal service address

Redis runs in local Compose. The current Rainyun template is a LiteLLM + PostgreSQL two-container setup. Add Redis to the cloud architecture when you scale replicas or need cross-instance rate limiting, routing state, and cache.

Public entry points (replace the domain with your current Rainyun website-proxy domain):

| Purpose | Local | Public |
| --- | --- | --- |
| Admin UI | `http://localhost:3029/ui/` | `https://your-domain/ui/` |
| Readiness check | `http://localhost:3029/health/readiness` | `https://your-domain/health/readiness` |
| OpenAI-compatible API | `http://localhost:3029/v1/` | `https://your-domain/v1/` |
| Cursor Base URL | `http://localhost:3029/cursor` | `https://your-domain/cursor` |

Day-to-day entry points are `/ui/`, `/v1/`, and `/cursor`. Local and Rainyun Compose set `NO_DOCS`, `NO_REDOC`, and `NO_OPENAPI` to `True`.

Local Docker idle measurements:

- LiteLLM: about `740-761 MiB`
- PostgreSQL: about `55-57 MiB`
- Total: about `795-818 MiB`

Current cloud deploy recommendations:

- First start or migration: LiteLLM `2 vCPU`, `2048 MB`
- Stable low concurrency: LiteLLM `1 vCPU`, `1024 MB`
- PostgreSQL: `0.5 vCPU`, `256 MB`
- Available project memory: at least `2 GB`
- LiteLLM replica count: `1`
- Worker count: `1`

Use the same sizing for local testing. Keep a personal Cursor gateway at a single replica; cross-instance rate limiting, routing state, and cache require shared Redis and a load balancer.

`1024 MB` is only suitable for personal low concurrency. If OOM occurs during long Agent tasks, parallel tool calls, or database migrations, raise LiteLLM to `2048 MB`.

## 2. Secrets

Deploy with three distinct random values:

| Variable | Purpose | Requirement |
| --- | --- | --- |
| `LITELLM_MASTER_KEY` | Admin UI password and highest-privilege API Key | Must start with `sk-` |
| `LITELLM_SALT_KEY` | Encrypts upstream credentials in the database | Must start with `sk-`; do not change it after you add models |
| `POSTGRES_PASSWORD` | PostgreSQL user password | Use a long random value |

Security requirements:

- Keep real secrets on the local `.env` or the deploy platform, never in Git
- Cursor uses only a restricted Virtual Key
- Master Key and Salt Key are for the gateway and admin UI only
- Keep `LITELLM_SALT_KEY` unchanged after it has encrypted model credentials
- The full Virtual Key is usually shown only once; save it immediately after creation
- Immediately revoke and regenerate any secret that has appeared in chat, screenshots, logs, or a public repository

## 3. Local Deploy

### 3.1 Prerequisites

Install Docker Desktop or Docker Engine, and confirm Docker Compose is available.

### 3.2 Generate `.env`

Windows PowerShell:

```powershell
.\scripts\init.ps1
```

Linux or macOS:

```sh
chmod +x ./scripts/init.sh
./scripts/init.sh
```

The script generates:

```text
LITELLM_MASTER_KEY=sk-random-value
LITELLM_SALT_KEY=sk-random-value
POSTGRES_PASSWORD=random-value
PUBLIC_BASE_URL=http://localhost:3029
```

If `.env` already exists, the script does not overwrite it.

### 3.3 Start

```sh
docker compose up -d --build
docker compose ps
```

View logs:

```sh
docker compose logs -f litellm
docker compose logs -f db
```

Open `http://localhost:3029/health/readiness`. After it returns success, open `http://localhost:3029/ui/`.

Admin UI login:

```text
Username: UI_USERNAME in .env, default admin
Password: UI_PASSWORD in .env
```

### 3.4 Stop and Clean Up

Stop containers and keep data:

```sh
docker compose down
```

Remove containers and all local database data:

```sh
docker compose down -v
```

`docker compose down -v` deletes the local database volume. Use it only when you intend to wipe the data.

## 4. Current Production: Rainyun RCA Cloud-App Deploy

This project is not Docker run by hand on a generic VPS. It is deployed as a Rainyun RCA (Rain Cloud Apps) cloud app. RCA runs apps on container orchestration and supports multi-container Compose import, internal service discovery between containers, resource limits, persistent volumes, and website proxy.

[![Deploy on RainYun](https://rainyun-apps.cn-nb1.rains3.com/materials/deploy-on-rainyun-en.svg)](https://www.rainyun.com/Nzc5MDEw_)

New accounts should use [this Rainyun link](https://www.rainyun.com/Nzc5MDEw_) to open the console, then follow the steps below to import `rainyun-compose.yml`.

Console names may change across versions; in this document, `应用模板` (app template), `版本编辑` (version editor), and `从 Docker 导入` (import from Docker) refer to the matching entries in the current console. Rainyun official docs confirm that after Compose import, a container can get another container's internal address through `${rca_svc_[container-name]_[service-name]}`.

### 4.1 Current Deploy Topology

```text
Cursor
  ↓ HTTPS
Rainyun website proxy / custom domain
  ↓ external service api:4000
litellm
  ↓ ${rca_svc_db_postgres}:5432
PostgreSQL
```

Only LiteLLM's `4000` service is exposed to the public internet. PostgreSQL uses an internal service and must not be exposed publicly.

### 4.2 Generate Three Secrets

Windows PowerShell 5.1 and later:

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

Save them as `LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, and `POSTGRES_PASSWORD`.

### 4.3 Import Compose

1. Sign in to the Rainyun console and open `云应用` (cloud apps).
2. Create a project and make sure at least `2 GB` of memory is still available to allocate.
3. Create a personal `应用模板` (app template) and a new version.
4. Choose `从 Docker 导入` (import from Docker).
5. Import `rainyun-compose.yml` from the repository root.
6. Confirm that both the `litellm` and `db` containers appear.
7. Confirm that `litellm` exposes `4000/TCP` and that `db` only provides the `5432/TCP` internal service.

`rainyun-compose.yml` uses placeholders that can be parsed as-is. The Rainyun importer only resolves platform-generated `${rca_svc_*}` references; replace the remaining `replace-with-...` secrets with real values in the import UI before you install.

The `litellm` service sets `pull_policy: always`. When Rainyun keeps that field, every redeploy checks and pulls the project's `latest` image. This setting does not rebuild the app on a schedule, and it does not automatically update the LiteLLM base version pinned in `litellm/Dockerfile`. Upgrades still require changing the pinned version, publishing a new image through CI, then redeploying on Rainyun.

### 4.4 Configure the `litellm` Container

Resources:

```text
First start CPU: 2000m
First start memory: 2048 MB
After stable, you can try CPU: 1000m
After stable, you can try memory: 1024 MB
```

Environment variables:

```text
DATABASE_URL=postgresql://litellm:database-password@${rca_svc_db_postgres}/litellm
LITELLM_MASTER_KEY=sk-your-MasterKey
LITELLM_SALT_KEY=sk-your-SaltKey
STORE_MODEL_IN_DB=True
NO_DOCS=True
NO_REDOC=True
NO_OPENAPI=True
```

Requirements:

- In `DATABASE_URL`, replace only the password portion
- Keep `${rca_svc_db_postgres}`
- Keep Command and Args empty
- The image ships with startup args `--config /app/config.yaml --port 4000 --num_workers 1`

If startup fails, keep Command and Args empty so the image uses the built-in `--config /app/config.yaml --port 4000 --num_workers 1`.

External service:

```text
Service name: api
Display name: LiteLLM
Service type: external access
Internal port: 4000
Protocol: TCP
```

### 4.5 Configure the `db` Container

Resources:

```text
CPU: 500m
Memory: 256 MB
```

Environment variables:

```text
POSTGRES_DB=litellm
POSTGRES_USER=litellm
POSTGRES_PASSWORD=same database password as DATABASE_URL
```

Internal service:

```text
Service name: postgres
Display name: PostgreSQL
Service type: internal access
Internal port: 5432
Protocol: TCP
```

`${rca_svc_db_postgres}` depends on container name `db` and service name `postgres`. Keep both names unchanged.

### 4.6 Configure Database Persistence

Confirm the `db` container has:

```text
Name: postgres-data
Mount path: /var/lib/postgresql/data
Subpath: llm-gateway-lite/postgres
Content type: directory
```

Without a persistence mount, rebuilding the container drops models, upstream credentials, Virtual Keys, budgets, and usage records.

### 4.7 Install and HTTPS

1. Confirm the page contains no `replace-with-` placeholders.
2. Save the template version and install the app.
3. Wait for PostgreSQL initialization and LiteLLM database migrations to finish.
4. In website management, add an `应用代理` (app proxy) site.
5. Select the `api` service on the `litellm` container.
6. Use a Rainyun domain or a custom domain.
7. Enable HTTPS.

Ordinary admin UI and Cursor access do not require `PROXY_BASE_URL`. Add it only when you use capabilities that generate external callback URLs, such as SSO or MCP OAuth:

```text
PROXY_BASE_URL=https://your-domain
```

The value is protocol plus domain only, with no trailing slash or path.

Check in this order:

```text
https://your-domain/health/liveliness
https://your-domain/health/readiness
https://your-domain/ui/
https://your-domain/cursor
```

A `307` from `/cursor` to `/cursor/` is expected. Hitting `/cursor/` with no API Key and getting `401` means the route exists and auth is in effect.

## 5. LiteLLM Admin UI Setup

### 5.1 Sign In

Open `https://your-domain/ui/`.

Local Compose uses `UI_USERNAME` / `UI_PASSWORD` from `.env`. When the Rainyun template does not set those two, the admin UI password is `LITELLM_MASTER_KEY` and the username defaults to `admin`.

### 5.2 Add a Standard Official OpenAI Model

Go to `Models + Endpoints` → `Add Model`:

```text
Provider: OpenAI
Public Model Name: gpt-4.1
LiteLLM Model Name: openai/gpt-4.1
API Key: OpenAI API Key
API Base: leave empty
```

### 5.3 Add a Standard OpenAI-Compatible Upstream

```text
Provider: OpenAI or OpenAI Compatible
Public Model Name: my-model
LiteLLM Model Name: openai/actual-upstream-model-name
API Key: upstream API Key
API Base: https://upstream-host/v1
```

Set `API Base` to the API root, for example `https://api.orangecc.cc/v1` or `https://api.orangecc.cc`.

### 5.4 Add an Official Anthropic Model

```text
Provider: Anthropic
Public Model Name: claude-sonnet
LiteLLM Model Name: anthropic/actual-upstream-model-name
API Key: Anthropic-compatible upstream API Key
API Base: https://upstream-root
```

For OrangeCC's Kiro Claude channel, use:

```text
LiteLLM Model Name: anthropic/claude-sonnet-5
API Base: https://api.orangecc.cc
```

LiteLLM calls that channel with the Anthropic protocol, and Request Logs show `anthropic`. Grok and GPT use `openai/responses/...`, which maps to OrangeCC's OpenAI Responses entry.

Azure OpenAI must use the Azure Provider and be configured with Azure's deployment name, Endpoint, and API Version. Do not reuse the ordinary OpenAI-compatible example.

### 5.5 Field Meanings

- `Public Model Name`: the name LiteLLM exposes to clients, and the model name you add in Cursor
- `LiteLLM Model Name`: LiteLLM's internal name for choosing the vendor, protocol, and upstream model
- `API Base`: upstream API root
- `API Key`: upstream vendor secret; LiteLLM encrypts it with the Salt Key before saving
- `RPM`, `TPM`: request and token limits of the upstream deployment; leave empty if unsure

The same Public Model Name can have multiple deployments; LiteLLM routes among them. Get the actual upstream model name from the vendor docs or `/v1/models`.

## 6. Responses-only Upstream Setup

Some OpenAI-compatible upstreams expose `/v1/chat/completions` but reject that path and only allow `/v1/responses`. Typical symptom:

```text
Provider returned error:
litellm.APIError: APIError: OpenAIException - Your request was blocked.
Received Model Group=model-name
Available Model Group Fallbacks=None
code=403
```

Test the upstream separately first:

- `/v1/chat/completions` returns `403 Your request was blocked`
- `/v1/responses` returns normally

Cursor uses Chat Completions. Keep the Public Model Name for clients, switch the internals to a Responses bridge, and verify in Playground with `/v1/chat/completions`:

```text
Public Model Name: gpt-5.6-sol
LiteLLM Model Name: openai/responses/gpt-5.6-sol
API Base: https://xfpa.orangecc.cc/v1
Provider: OpenAI
```

The `model` in LiteLLM Params should also be:

```text
openai/responses/gpt-5.6-sol
```

`openai/responses/` makes LiteLLM accept `/v1/chat/completions` requests, call the upstream Responses API internally, then return a standard Chat Completions shape. In Cursor, enter Public Model Name `gpt-5.6-sol`.

After the change, you must select this in Playground:

```text
Endpoint Type: /v1/chat/completions
Model: gpt-5.6-sol
```

Only a successful test here proves the path Cursor needs is bridged.

Keep ordinary Chat Completions upstreams as `openai/upstream-model-name`. Use `openai/responses/` only for models that accept `/v1/responses` only, or that you explicitly send through Responses.

## 7. Create a Virtual Key

1. Finish the `/v1/chat/completions` test in Playground.
2. Open `Virtual Keys`.
3. Choose `Create New Key`.
4. Set a recognizable Alias.
5. In Models, select only the Public Model Names you want to expose.
6. Set budget, RPM, TPM, and expiration as needed.
7. Save the full Key immediately after creation.

Cursor uses a Virtual Key. Master Key, Salt Key, and upstream vendor keys are for the gateway only. If the key's Models list does not include the target Public Model Name, the request fails due to model access limits.

## 8. Cursor Setup

In Cursor Models settings:

1. Enable OpenAI API Key.
2. Paste the Virtual Key created in LiteLLM.
3. Enable `Override OpenAI Base URL`.
4. Set Base URL to `https://your-domain/cursor`.
5. Add the LiteLLM Public Model Name.
6. Select that model and start testing.

Example:

```text
Base URL: https://your-domain/cursor
API Key: LiteLLM Virtual Key
Model: gpt-5.6-sol
```

This project's Cursor entry is `/cursor`, and the model name is the Public Model Name. For Grok, enter a tier name such as `grok-46-high`.

## 9. Full Capability Verification

A successful plain-text reply only proves basic generation works. Verify the Agent toolchain in the stages below.

### 9.1 Admin UI Verification

In LiteLLM Playground:

1. Select `/v1/chat/completions`.
2. Select the target Public Model Name.
3. Send an ordinary message.
4. Confirm that non-streaming or streaming responses are normal.
5. Confirm there is no `403`, missing model, or parameter error.

### 9.2 Cursor Staged Verification

Test in this order:

1. Ask: ordinary multi-turn text chat
2. Plan: read the repository and produce a plan
3. Agent: read files and search code
4. Agent: run terminal commands
5. Agent: create a temporary file
6. Agent: read and modify the temporary file
7. Agent: delete the temporary file
8. Agent: call multiple tools in sequence
9. Agent: continue reasoning after tool results return
10. Agent: confirm the Git working tree has no test leftovers

Currently verified `gpt-5.6-sol` path:

```text
Cursor
→ LiteLLM /cursor
→ /v1/chat/completions
→ openai/responses/gpt-5.6-sol bridge
→ upstream /v1/responses
```

Already verified in practice:

- Multi-turn chat
- Web search
- File listing
- Code search
- File read
- File create
- File edit
- File delete
- PowerShell and Python terminal commands
- Git status check
- Parallel multi-tool calls
- Continued reasoning after tool results return

This does not automatically guarantee every advanced capability. Image understanding, very long context, MCP, complex tool arguments, automatic recovery from tool failures, and long-running Agent tasks still need targeted verification against the actual model and usage scenario.

## 10. Cloud Day-to-Day Ops, Backup, and Upgrades

### 10.1 Daily Checks

After every change to models, secrets, or a Rainyun version, check in this order:

```text
1. Rainyun app status: litellm and db are both running
2. https://your-domain/health/liveliness
3. https://your-domain/health/readiness
4. https://your-domain/ui/
5. LiteLLM Logs show startup and database migrations completed
6. In Playground, test one model with /v1/chat/completions
7. In Cursor, test Ask, Plan, and Agent in order
```

`liveliness` mainly proves the process is alive; `readiness` also considers whether the database and services are ready. A site that opens does not mean the model path works.

### 10.2 Redeploy on Rainyun

The current `rainyun-compose.yml` uses:

```text
ghcr.io/ninthless/llm-gateway-lite:latest
```

`pull_policy: always` only means a redeploy checks and pulls the latest image. It does not mean the image updates on a schedule. Standard flow:

1. Change `litellm/Dockerfile` or project code.
2. Pass static checks, Compose checks, and smoke checks in GitHub Actions.
3. After CI succeeds, publish the new GHCR image.
4. Redeploy the app on Rainyun so `litellm` pulls the new image.
5. Watch LiteLLM logs and wait for database migrations to finish.
6. Re-verify health checks, admin UI login, models, Virtual Keys, and Cursor.

If you only change models, upstream URLs, or Virtual Keys in the admin UI, you do not need to rebuild the image; that data lives in PostgreSQL.

### 10.3 Backup These Together

Always back up together:

- PostgreSQL persistent volume
- `LITELLM_SALT_KEY`
- `LITELLM_MASTER_KEY`
- `POSTGRES_PASSWORD`

If you back up only the database and lose the Salt Key, encrypted upstream API Keys cannot be recovered.

### 10.4 Upgrade Procedure

Upgrade procedure:

1. Back up the database volume and the three secrets.
2. In a test environment, change the pinned version in `litellm/Dockerfile`.
3. Rebuild the image.
4. Verify database migrations.
5. Verify admin UI login, model reads, and upstream credential decryption.
6. Verify Virtual Key permissions.
7. Verify Ask, Plan, Agent, tool calls, file edits, and streaming output.
8. Update production only after verification.

Production pins the version in `litellm/Dockerfile`. LiteLLM `/cursor`, Responses bridging, parameter translation, and Admin UI behavior can all change across versions.

## 11. Known Issues and Troubleshooting

### 11.1 Rainyun Returns `Bad Gateway` or `no available server`

Meaning: the HTTPS site is up, but there is no available LiteLLM process behind container port `4000`.

Action:

1. Give LiteLLM `2 vCPU` and `2048 MB` on first start.
2. Keep Command and Args empty.
3. Check that all three placeholder secrets were replaced.
4. Check that `DATABASE_URL` still contains `${rca_svc_db_postgres}`.
5. Check that the database password matches `POSTGRES_PASSWORD` exactly.
6. Check the `db` container name, `postgres` service name, and `5432` port.
7. Look for Prisma migration errors in LiteLLM logs.
8. Check `/health/liveliness` first, then `/health/readiness`.

If LiteLLM has no logs at all, first check whether the container command was overwritten by the Rainyun form, and whether memory is too low to start.

### 11.2 PostgreSQL Shows Locale or `trust` Warnings

`postgres:16-alpine` uses musl and may show:

```text
locale: not found
no usable system locales were found
```

During init you may also see a note that the local Unix socket uses `trust`. As long as the logs eventually show:

```text
database system is ready to accept connections
```

the database is ready. A temporary start, stop, and official start again during initialization is expected.

### 11.3 LiteLLM Keeps Restarting

Check:

- Whether `DATABASE_URL` is correct
- Whether `${rca_svc_db_postgres}` is preserved
- Whether the database password matches
- Whether `LITELLM_MASTER_KEY` and `LITELLM_SALT_KEY` are non-empty and start with `sk-`
- Whether PostgreSQL is ready
- Whether Prisma migration failed
- Whether memory hit OOM

### 11.4 Cannot Sign In to the Admin UI

Locally, use `UI_USERNAME` / `UI_PASSWORD`. When the Rainyun template does not set those two, the username defaults to `admin` and the password is `LITELLM_MASTER_KEY`. Restart LiteLLM after you change the Master Key or UI password. Virtual Keys are for the API only.

### 11.5 Calls Fail After Adding a Model

Check in this order:

1. Whether API Base is the correct API root
2. Whether LiteLLM Model Name includes the correct vendor prefix
3. Whether the actual upstream model name exists
4. Whether the upstream API Key is valid
5. Whether the upstream supports Chat Completions or Responses
6. Whether Playground's target Endpoint Type matches the Cursor path
7. Whether the Virtual Key allows that Public Model Name

Test in the admin UI Playground first, then test Cursor.

### 11.6 Cursor Returns `403 Your request was blocked`

If the LiteLLM error also includes:

```text
OpenAIException - Your request was blocked
Received Model Group=...
Available Model Group Fallbacks=None
```

this usually means the upstream rejected the Chat Completions request sent by LiteLLM.

After you confirm that upstream `/v1/responses` works and `/v1/chat/completions` is rejected, change LiteLLM Model Name to:

```text
openai/responses/actual-upstream-model-name
```

Keep Public Model Name unchanged, then retest in Playground with `/v1/chat/completions`.

### 11.7 Playground Responses Test Succeeds, but Cursor Fails

Cause: testing `/v1/responses` directly in Playground does not cover Cursor's Chat Completions entry.

Fix: explicitly select `/v1/chat/completions` in Playground. For Responses-only upstreams, use the `openai/responses/` internal model name.

### 11.8 Ordinary Chat Works, but Agent Tools Fail

Ordinary chat does not cover:

- Tool schema translation
- Tool call streaming events
- Multi-turn Tool result
- Parallel tool calls
- File edits
- Terminal calls

Run the full capability verification in section 9. If it fails, use the Request ID in LiteLLM Logs to inspect request parameters and upstream errors.

### 11.9 `Available Model Group Fallbacks=None`

This means the target Model Group has no usable fallback configured. The real cause is usually the upstream status code and message in the same error.

A personal single-upstream deploy can skip fallback. For high availability, add multiple working deployments under the same Public Model Name or configure fallback explicitly, and verify protocol compatibility for each.

### 11.10 Wrong Cursor Base URL

This project uses:

```text
https://your-domain/cursor
```

A `307` redirect from `/cursor` and a `401` from unauthenticated `/cursor/` are both expected.

### 11.11 Virtual Key Cannot Access the Model

Check whether the Virtual Key's Models list includes the target Public Model Name. Cursor fills in the Public Model Name.

### 11.12 Data Loss After Rebuild

Check that `db` has a persistence mount:

```text
/var/lib/postgresql/data
```

Keep the corresponding subpath in the Docker Volume and the Rainyun shared disk.

### 11.13 Upstream Credentials Fail After Changing Salt Key

The Salt Key encrypts upstream credentials in the database. Restore the original Salt Key, or re-enter every upstream API Key. A new Salt Key cannot decrypt old data.

### 11.14 Out of Memory or Frequent Restarts

Action:

- Raise LiteLLM to `1536-2048 MB`
- Keep total project memory at least `2 GB`
- Keep `--num_workers 1`
- Run only one LiteLLM replica for a personal deploy
- Try lowering resources only after the first migration has finished

### 11.15 Rainyun Compose Import Reports Missing Environment Variables

Rainyun cannot resolve arbitrary nested `${VAR}` during import. Use the repository `rainyun-compose.yml`, keep only the platform-required `${rca_svc_db_postgres}`, and use placeholders for the other secrets, then replace them in the import UI.

### 11.16 GHCR Image Pull Fails

Confirm:

- The image name is `ghcr.io/ninthless/llm-gateway-lite:latest`
- GitHub Packages allows public anonymous pulls for that image
- The Rainyun node can reach GHCR
- The image build workflow has successfully published the matching architecture

### 11.17 Model Config Does Not Update After Editing

Open the model details and confirm:

- The top `LiteLLM Model` already shows the new value
- `model` in `LiteLLM Params` already shows the new value
- The page shows a save-success message

Then go back to Playground and reselect the model. Refresh the model list if needed.

### 11.18 Request ID in Logs

When Cursor errors, keep the full error and Request ID. Use LiteLLM `Logs` to locate the matching request by time, model, and status code. Put API Key, Authorization Header, and full credentials only in private channels.

### 11.19 OrangeCC Returns Cloudflare `502 Bad gateway`

If the error body contains:

```text
orangecc.cc | 502: Bad gateway
Cloudflare
api.orangecc.cc
```

LiteLLM already sent the request to OrangeCC, but OrangeCC's Cloudflare did not get a normal response from the origin. First check the model protocol:

- GPT / Grok: `openai/responses/...` and upstream `/v1/responses`
- Claude: `anthropic/claude-*` and the OrangeCC Anthropic channel

Current Claude config:

```text
LiteLLM Model Name: anthropic/claude-sonnet-5
API Base: https://api.orangecc.cc
```

Retest in the same cloud environment and record the time, model, and Request ID. If both a direct call and LiteLLM return Cloudflare 502, contact the upstream or wait for it to recover.

### 11.20 Request Logs Show `openai` or `anthropic`

The Provider in Request Logs depends on the LiteLLM Model Name prefix:

```text
openai/responses/grok-4.6  → openai
anthropic/claude-sonnet-5  → anthropic
```

`openai` in Request Logs means LiteLLM selected the OpenAI Responses adapter; the target is still the configured API Base. Claude uses `anthropic/claude-*`.

## 12. Security Checklist

- Expose only the LiteLLM `4000` service publicly, through an HTTPS website proxy
- Keep PostgreSQL `5432` internal-only
- Point the Rainyun website proxy at LiteLLM `api:4000`
- Cursor uses only a restricted Virtual Key, with model scope, budget, and rate limits
- Master Key and Salt Key are for the gateway only
- Keep `.env` on the local machine or the deploy platform
- Keep the Salt Key unchanged after it has encrypted credentials
- Regularly back up the database volume and the three secrets
- Revoke upstream or Virtual Keys immediately if they leak
- Verify the full Agent toolchain in a test environment before upgrading
- Before a production upgrade, confirm the GHCR image built successfully and keep rollback information for the previous version

## 13. Project Check Commands

```sh
node tests/check-static.mjs
docker compose config --quiet
docker compose -f rainyun-compose.yml config --no-interpolate --quiet
docker build -t llm-gateway-lite ./litellm
```

Runtime status:

```sh
docker compose ps
docker compose logs -f litellm
docker compose logs -f db
```

## 14. Sources

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
- [LiteLLM Proxy Configs: NO_DOCS / NO_REDOC](https://docs.litellm.ai/docs/proxy/configs)
- [Rainyun referral](https://www.rainyun.com/Nzc5MDEw_)
- [Rainyun cloud apps Docker Compose update](https://forum.rainyun.com/t/topic/12843)
- [Rainyun app version tutorial](https://forum.rainyun.com/t/topic/11296)
- [Rainyun cloud apps quick start](https://www.rainyun.com/docs/products/rca/start.html)
- [Rainyun app management](https://www.rainyun.com/docs/products/rca/project/apps.html)
