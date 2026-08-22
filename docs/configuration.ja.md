# LLM Gateway Lite 設定とトラブルシュート

[English](configuration.md) | [简体中文](configuration.zh-CN.md) | **日本語**

この文書は現行の本番環境に合わせ、Rainyun RCA クラウドアプリ展開、クラウド運用、ローカル Docker テスト、LiteLLM 管理 UI、上流モデル、Virtual Key、Cursor 接続、能力検証、バックアップ／アップグレード、既知の問題を扱う。

現行の本番展開は Rainyun RCA クラウドアプリです。LiteLLM イメージは GitHub Container Registry から提供し、データベースは PostgreSQL です。イメージ内部では LiteLLM Proxy `v1.98.0-rc.1` を固定しています。アップグレードでは、先に `litellm/Dockerfile` の固定バージョンを変更し、CI で公開してからデプロイします。

## 1. アーキテクチャ、ポート、リソース

ローカル Docker Compose は 3 つのコンテナで構成されます。

- `litellm`：LiteLLM Proxy、公式管理 UI、OpenAI 互換インターフェース、Cursor インターフェース
- `db`：PostgreSQL。モデル、資格情報、Virtual Key、予算、利用量データを保存します
- `redis`：ルーティング協調、レート制限の状態、キャッシュ

本番の Rainyun RCA テンプレートは 2 つのコンテナです。

- `litellm`：`ghcr.io/ninthless/llm-gateway-lite:latest` から取得
- `db`：PostgreSQL。RCA 内部ネットワークのサービスアドレスで接続します

Redis はローカル Compose で動作します。現行の Rainyun テンプレートは LiteLLM + PostgreSQL の 2 コンテナです。レプリカを増やす、またはインスタンスをまたぐレート制限、ルーティング状態、キャッシュが必要なときは、Redis をクラウド構成に加えてください。

対外入口（ドメインは現行の Rainyun サイトプロキシドメインに置き換えてください）：

| 用途 | ローカルアドレス | 公開アドレス |
| --- | --- | --- |
| 管理 UI | `http://localhost:3029/ui/` | `https://your-domain/ui/` |
| 準備確認 | `http://localhost:3029/health/readiness` | `https://your-domain/health/readiness` |
| OpenAI 互換インターフェース | `http://localhost:3029/v1/` | `https://your-domain/v1/` |
| Cursor Base URL | `http://localhost:3029/cursor` | `https://your-domain/cursor` |

日常の入口は `/ui/`、`/v1/`、`/cursor` です。ローカルと Rainyun の Compose では `NO_DOCS`、`NO_REDOC`、`NO_OPENAPI` を `True` にしています。

ローカル Docker のアイドル時実測：

- LiteLLM：約 `740-761 MiB`
- PostgreSQL：約 `55-57 MiB`
- 合計：約 `795-818 MiB`

現行のクラウド展開の目安：

- 初回起動または移行：LiteLLM `2 vCPU`、`2048 MB`
- 安定した低同時実行：LiteLLM `1 vCPU`、`1024 MB`
- PostgreSQL：`0.5 vCPU`、`256 MB`
- プロジェクトの利用可能メモリ：少なくとも `2 GB`
- LiteLLM のレプリカ数：`1`
- Worker 数：`1`

ローカルテストの目安もクラウドと同じです。個人向け Cursor ゲートウェイは単一レプリカのままにしてください。インスタンスをまたぐレート制限、ルーティング状態、キャッシュには、共有 Redis とロードバランサが必要です。

`1024 MB` は個人の低同時実行向けです。Agent の長時間タスク、並列ツール呼び出し、またはデータベース移行中に OOM が出たら、LiteLLM を `2048 MB` に上げてください。

## 2. キーの説明

展開には、互いに異なるランダム値が 3 つ必要です。

| 変数 | 用途 | 要件 |
| --- | --- | --- |
| `LITELLM_MASTER_KEY` | 管理 UI の管理者パスワードと最上位権限の API Key | 必ず `sk-` で始める |
| `LITELLM_SALT_KEY` | データベース内の上流資格情報を暗号化 | 必ず `sk-` で始める。モデル追加後は変更しない |
| `POSTGRES_PASSWORD` | PostgreSQL ユーザーパスワード | 長いランダム値を使う |

セキュリティ要件：

- 実キーは手元の `.env` または展開プラットフォームに置き、Git に入れない
- Cursor には権限を絞った Virtual Key だけを使う
- Master Key、Salt Key はゲートウェイと管理 UI 専用
- `LITELLM_SALT_KEY` はモデル資格情報を暗号化したあと変更しない
- 完全な Virtual Key は通常 1 回しか表示されないので、作成直後に保存する
- チャット、スクリーンショット、ログ、公開リポジトリに出たキーは、すぐに失効させて再生成する

## 3. ローカル展開

### 3.1 前提条件

Docker Desktop または Docker Engine をインストールし、Docker Compose が使えることを確認してください。

### 3.2 `.env` を生成する

Windows PowerShell：

```powershell
.\scripts\init.ps1
```

Linux または macOS：

```sh
chmod +x ./scripts/init.sh
./scripts/init.sh
```

スクリプトは次を生成します。

```text
LITELLM_MASTER_KEY=sk-ランダム値
LITELLM_SALT_KEY=sk-ランダム値
POSTGRES_PASSWORD=ランダム値
PUBLIC_BASE_URL=http://localhost:3029
```

`.env` が既にある場合、スクリプトは上書きしません。

### 3.3 起動

```sh
docker compose up -d --build
docker compose ps
```

ログを見る：

```sh
docker compose logs -f litellm
docker compose logs -f db
```

`http://localhost:3029/health/readiness` にアクセスしてください。成功したら `http://localhost:3029/ui/` を開きます。

管理 UI のログイン情報：

```text
ユーザー名：.env の UI_USERNAME、既定は admin
パスワード：.env の UI_PASSWORD
```

### 3.4 停止とクリーンアップ

コンテナを停止し、データは残す：

```sh
docker compose down
```

コンテナとローカルのデータベースデータをすべて削除する：

```sh
docker compose down -v
```

`docker compose down -v` はローカルのデータベースボリュームを削除します。データを空にすると決めたときだけ使ってください。

## 4. 現行本番環境：Rainyun RCA クラウドアプリ展開

現行プロジェクトは、普通の VPS 上で Docker を手作業実行する構成ではありません。Rainyun RCA（Rain Cloud Apps）クラウドアプリに展開します。RCA はコンテナオーケストレーションでアプリを動かし、複数コンテナの Compose 取り込み、コンテナ間の内部サービス検出、リソース制限、永続ボリューム、サイトプロキシをサポートします。

[![Deploy on RainYun](https://rainyun-apps.cn-nb1.rains3.com/materials/deploy-on-rainyun-en.svg)](https://www.rainyun.com/Nzc5MDEw_)

新規アカウントは [この Rainyun リンク](https://www.rainyun.com/Nzc5MDEw_) からコンソールに入り、次の手順で `rainyun-compose.yml` を取り込んでください。

コンソールの名称はバージョンで変わることがあります。本文の `应用模板`（アプリテンプレート）、`版本编辑`（バージョン編集）、`从 Docker 导入`（Docker から取り込み）は、現行コンソールの対応する入口を指します。Rainyun の公式資料では、Compose 取り込み後のコンテナは `${rca_svc_[容器名]_[服务名]}` で別コンテナの内部アドレスを取得できます。

### 4.1 現行の展開トポロジ

```text
Cursor
  ↓ HTTPS
Rainyun サイトプロキシ / カスタムドメイン
  ↓ 外部サービス api:4000
litellm
  ↓ ${rca_svc_db_postgres}:5432
PostgreSQL
```

公開網に出すのは LiteLLM の `4000` サービスだけです。PostgreSQL は内部サービスにし、公開網へ出さないでください。

### 4.2 3 つのキーを生成する

Windows PowerShell 5.1 以上：

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

それぞれ `LITELLM_MASTER_KEY`、`LITELLM_SALT_KEY`、`POSTGRES_PASSWORD` として保存してください。

### 4.3 Compose を取り込む

1. Rainyun コンソールにログインし、`云应用`（クラウドアプリ）に入る。
2. プロジェクトを作成し、割り当て可能なメモリが少なくとも `2 GB` 残っていることを確認する。
3. 個人の `应用模板`（アプリテンプレート）と新しいバージョンを作成する。
4. `从 Docker 导入`（Docker から取り込み）を選ぶ。
5. リポジトリルートの `rainyun-compose.yml` を取り込む。
6. `litellm` と `db` の 2 コンテナが出ることを確認する。
7. `litellm` が `4000/TCP` を公開し、`db` は `5432/TCP` の内部サービスだけを提供することを確認する。

`rainyun-compose.yml` は、そのまま解釈できるプレースホルダ値を使います。Rainyun の取り込み処理が解決するのは、プラットフォームが生成する `${rca_svc_*}` 参照だけです。残りのキーは、取り込み画面で `replace-with-...` を実値に替えてからインストールしてください。

`litellm` サービスには `pull_policy: always` が付いています。Rainyun がこのフィールドを残す場合、再デプロイのたびにプロジェクトの `latest` イメージを確認して取得します。この設定はアプリを定時再構築せず、`litellm/Dockerfile` に固定した LiteLLM ベースバージョンも自動更新しません。アップグレードでは、先に固定バージョンを変更し、CI で新しいイメージを公開してから、Rainyun で再デプロイしてください。

### 4.4 `litellm` コンテナを設定する

リソース：

```text
初回起動 CPU：2000m
初回起動メモリ：2048 MB
安定後に試せる CPU：1000m
安定後に試せるメモリ：1024 MB
```

環境変数：

```text
DATABASE_URL=postgresql://litellm:データベースパスワード@${rca_svc_db_postgres}/litellm
LITELLM_MASTER_KEY=sk-あなたのMasterKey
LITELLM_SALT_KEY=sk-あなたのSaltKey
STORE_MODEL_IN_DB=True
NO_DOCS=True
NO_REDOC=True
NO_OPENAPI=True
```

要件：

- `DATABASE_URL` はパスワード部分だけを置き換える
- `${rca_svc_db_postgres}` は必ず残す
- Command と Args は空のままにする
- イメージ同梱の起動引数は `--config /app/config.yaml --port 4000 --num_workers 1`

起動に失敗したら、Command と Args を空のままにして、イメージ内蔵の `--config /app/config.yaml --port 4000 --num_workers 1` を使わせてください。

外部サービス：

```text
サービス名：api
表示名：LiteLLM
サービスタイプ：外部アクセス
内部ポート：4000
プロトコル：TCP
```

### 4.5 `db` コンテナを設定する

リソース：

```text
CPU：500m
メモリ：256 MB
```

環境変数：

```text
POSTGRES_DB=litellm
POSTGRES_USER=litellm
POSTGRES_PASSWORD=DATABASE_URL と完全に同じデータベースパスワード
```

内部サービス：

```text
サービス名：postgres
表示名：PostgreSQL
サービスタイプ：内部アクセス
内部ポート：5432
プロトコル：TCP
```

`${rca_svc_db_postgres}` はコンテナ名 `db` とサービス名 `postgres` に依存します。この 2 つの名前は変えないでください。

### 4.6 データベースの永続化を設定する

`db` コンテナに次があることを確認してください。

```text
名前：postgres-data
マウントパス：/var/lib/postgresql/data
サブパス：llm-gateway-lite/postgres
コンテンツタイプ：ディレクトリ
```

永続マウントがないと、コンテナ再構築でモデル、上流資格情報、Virtual Key、予算、利用量の記録が消えます。

### 4.7 インストールと HTTPS

1. 画面に `replace-with-` プレースホルダが残っていないことを確認する。
2. テンプレートバージョンを保存し、アプリをインストールする。
3. PostgreSQL の初期化と LiteLLM のデータベース移行が終わるまで待つ。
4. サイト管理で `应用代理`（アプリプロキシ）サイトを追加する。
5. `litellm` コンテナの `api` サービスを選ぶ。
6. Rainyun ドメインまたはカスタムドメインを使う。
7. HTTPS を有効にする。

通常の管理 UI と Cursor 接続では `PROXY_BASE_URL` は不要です。SSO や MCP OAuth など、外部コールバック URL を生成する機能を使うときだけ追加してください。

```text
PROXY_BASE_URL=https://your-domain
```

この値はプロトコルとドメインだけです。末尾スラッシュやパスは付けません。

次の順で確認してください。

```text
https://your-domain/health/liveliness
https://your-domain/health/readiness
https://your-domain/ui/
https://your-domain/cursor
```

`/cursor` にアクセスして `307` で `/cursor/` へ飛ぶのは正常です。API Key なしで `/cursor/` に直接アクセスして `401` が返れば、ルートが存在し、認証が効いています。

## 5. LiteLLM 管理 UI の設定

### 5.1 ログイン

`https://your-domain/ui/` を開きます。

ローカル Compose は `.env` の `UI_USERNAME` / `UI_PASSWORD` を使います。Rainyun テンプレートでこの 2 つを設定していない場合、管理 UI のパスワードは `LITELLM_MASTER_KEY`、ユーザー名の既定は `admin` です。

### 5.2 通常の OpenAI 公式モデルを追加する

`Models + Endpoints` → `Add Model` に進みます。

```text
Provider：OpenAI
Public Model Name：gpt-4.1
LiteLLM Model Name：openai/gpt-4.1
API Key：OpenAI API Key
API Base：空のまま
```

### 5.3 通常の OpenAI 互換上流を追加する

```text
Provider：OpenAI または OpenAI Compatible
Public Model Name：my-model
LiteLLM Model Name：openai/上流の実際のモデル名
API Key：上流 API Key
API Base：https://上流アドレス/v1
```

`API Base` には API のルートアドレスを入れます。例：`https://api.orangecc.cc/v1` または `https://api.orangecc.cc`。

### 5.4 Anthropic 公式モデルを追加する

```text
Provider：Anthropic
Public Model Name：claude-sonnet
LiteLLM Model Name：anthropic/上流の実際のモデル名
API Key：Anthropic 互換の上流 API Key
API Base：https://上流のルートアドレス
```

OrangeCC の Kiro Claude チャネルでは次を使います。

```text
LiteLLM Model Name：anthropic/claude-sonnet-5
API Base：https://api.orangecc.cc
```

LiteLLM はこのチャネルを Anthropic プロトコルで呼び、Request Logs には `anthropic` と出ます。Grok と GPT は `openai/responses/...` を使い、OrangeCC の OpenAI Responses 入口に対応します。

Azure OpenAI は必ず Azure Provider を選び、Azure のデプロイ名、Endpoint、API Version で設定してください。通常の OpenAI 互換の例を流用しないでください。

### 5.5 フィールドの意味

- `Public Model Name`：LiteLLM がクライアントへ公開する名前。Cursor に追加するモデル名でもあります
- `LiteLLM Model Name`：LiteLLM がプロバイダ、プロトコル、上流モデルを選ぶ内部名
- `API Base`：上流 API のルートアドレス
- `API Key`：上流プロバイダのキー。LiteLLM が Salt Key で暗号化して保存します
- `RPM`、`TPM`：上流デプロイのリクエストと Token 制限。不明なら空のまま

同じ Public Model Name に複数デプロイを載せ、LiteLLM がルーティングできます。上流の実際のモデル名は、プロバイダのドキュメントまたは `/v1/models` から取得してください。

## 6. Responses-only 上流の設定

一部の OpenAI 互換上流は `/v1/chat/completions` を公開していても、そのパスを拒否し、`/v1/responses` だけを許可します。典型的な症状：

```text
Provider returned error:
litellm.APIError: APIError: OpenAIException - Your request was blocked.
Received Model Group=モデル名
Available Model Group Fallbacks=None
code=403
```

先に上流を個別にテストしてください。

- `/v1/chat/completions` が `403 Your request was blocked` を返す
- `/v1/responses` は正常に返す

Cursor は Chat Completions を使います。対外的な Public Model Name はそのまま、内部を Responses ブリッジに変え、Playground で `/v1/chat/completions` を検証してください。

```text
Public Model Name：gpt-5.6-sol
LiteLLM Model Name：openai/responses/gpt-5.6-sol
API Base：https://xfpa.orangecc.cc/v1
Provider：OpenAI
```

LiteLLM Params の `model` も次にしてください。

```text
openai/responses/gpt-5.6-sol
```

`openai/responses/` があると、LiteLLM は `/v1/chat/completions` を受け、内部で上流の Responses API を呼び、標準の Chat Completions 形状で返します。Cursor には Public Model Name `gpt-5.6-sol` を記入します。

変更後は、必ず Playground で次を選んでください。

```text
Endpoint Type：/v1/chat/completions
Model：gpt-5.6-sol
```

このテストが成功して初めて、Cursor が使うパスのブリッジができたと言えます。

通常の Chat Completions 上流は `openai/上流モデル名` のままです。`/v1/responses` だけを受け付ける、または明示的に Responses を通すモデルだけ `openai/responses/` を使ってください。

## 7. Virtual Key の作成

1. Playground で `/v1/chat/completions` テストを完了する。
2. `Virtual Keys` に入る。
3. `Create New Key` を選ぶ。
4. 識別しやすい Alias を設定する。
5. Models では開放したい Public Model Name だけを選ぶ。
6. 必要に応じて予算、RPM、TPM、有効期限を設定する。
7. 作成後、すぐに完全な Key を保存する。

Cursor には Virtual Key を使います。Master Key、Salt Key、上流プロバイダ Key はゲートウェイ専用です。Key の Models 一覧に対象の Public Model Name が無いと、モデルアクセス制限で失敗します。

## 8. Cursor の設定

Cursor の Models 設定で：

1. OpenAI API Key を有効にする。
2. LiteLLM で作った Virtual Key を記入する。
3. `Override OpenAI Base URL` を有効にする。
4. Base URL に `https://your-domain/cursor` を記入する。
5. LiteLLM の Public Model Name を追加する。
6. そのモデルを選んでテストを始める。

例：

```text
Base URL：https://your-domain/cursor
API Key：LiteLLM Virtual Key
Model：gpt-5.6-sol
```

このプロジェクトの Cursor 入口は `/cursor`、モデル名は Public Model Name です。Grok には `grok-46-high` のようなティア名を記入します。

## 9. 能力の完全検証

通常テキストが成功しただけでは、基礎生成ができることしか分かりません。Agent ツールチェーンは、次の段階で検証してください。

### 9.1 管理 UI での検証

LiteLLM Playground で：

1. `/v1/chat/completions` を選ぶ。
2. 対象の Public Model Name を選ぶ。
3. 通常のメッセージを送る。
4. 非ストリーミングまたはストリーミングの応答が正常なことを確認する。
5. `403`、モデル不存在、パラメータエラーが無いことを確認する。

### 9.2 Cursor の段階検証

次の順でテストしてください。

1. Ask：通常の複数ターンテキスト対話
2. Plan：リポジトリを読んで計画を生成
3. Agent：ファイル読み取りとコード検索
4. Agent：ターミナルコマンドの実行
5. Agent：一時ファイルの作成
6. Agent：一時ファイルの読み取りと変更
7. Agent：一時ファイルの削除
8. Agent：複数ツールの連続呼び出し
9. Agent：ツール結果が返ったあとの継続推論
10. Agent：Git 作業ツリーにテスト残骸が無いことを確認

現在検証済みの `gpt-5.6-sol` 経路：

```text
Cursor
→ LiteLLM /cursor
→ /v1/chat/completions
→ openai/responses/gpt-5.6-sol ブリッジ
→ 上流 /v1/responses
```

実際に通過した項目：

- 複数ターン対話
- Web 検索
- ファイル列挙
- コード検索
- ファイル読み取り
- ファイル作成
- ファイル変更
- ファイル削除
- PowerShell と Python のターミナルコマンド
- Git 状態確認
- 複数ツールの並列呼び出し
- ツール結果返却後の継続推論

これですべての高度な能力が自動保証されるわけではありません。画像理解、超長コンテキスト、MCP、複雑なツールパラメータ、ツール失敗時の自動復旧、長時間 Agent タスクは、実際のモデルと利用シーンごとに別途検証してください。

## 10. クラウドの日常運用、バックアップ、アップグレード

### 10.1 日常点検

モデル、キー、Rainyun バージョンを変更したあとは、次の順で確認してください。

```text
1. Rainyun アプリ状態：litellm と db がともに実行中
2. https://your-domain/health/liveliness
3. https://your-domain/health/readiness
4. https://your-domain/ui/
5. LiteLLM Logs で起動とデータベース移行が完了しているか
6. Playground で /v1/chat/completions を使ってモデルを 1 つテスト
7. Cursor で Ask、Plan、Agent を順にテスト
```

`liveliness` は主にプロセス生存を示し、`readiness` はデータベースとサービスが準備できているかも見ます。サイトが開けることと、モデル経路が使えることは別です。

### 10.2 Rainyun での再デプロイ

現行の `rainyun-compose.yml` は次を使います。

```text
ghcr.io/ninthless/llm-gateway-lite:latest
```

`pull_policy: always` は、再デプロイ時に最新イメージを確認して取得することを意味するだけで、イメージが自動で定時更新されるわけではありません。標準手順は次です。

1. `litellm/Dockerfile` またはプロジェクトコードを変更する。
2. GitHub Actions で静的検査、Compose 検査、smoke 検査を通す。
3. CI 成功後、新しい GHCR イメージを公開する。
4. Rainyun でアプリを再デプロイし、`litellm` に新しいイメージを取得させる。
5. LiteLLM ログを見て、データベース移行の完了を待つ。
6. ヘルスチェック、管理 UI ログイン、モデル、Virtual Key、Cursor を再検証する。

管理 UI 上のモデル、上流アドレス、Virtual Key だけを変える場合、イメージの再構築は不要です。これらのデータは PostgreSQL に保存されます。

### 10.3 必ず一緒にバックアップする

次は必ず一緒にバックアップしてください。

- PostgreSQL 永続ボリューム
- `LITELLM_SALT_KEY`
- `LITELLM_MASTER_KEY`
- `POSTGRES_PASSWORD`

データベースだけバックアップして Salt Key を失うと、暗号化済みの上流 API Key は復元できません。

### 10.4 アップグレード手順

アップグレード手順：

1. データベースボリュームと 3 つのキーをバックアップする。
2. テスト環境で `litellm/Dockerfile` の固定バージョンを変更する。
3. イメージを再構築する。
4. データベース移行を検証する。
5. 管理 UI ログイン、モデル読み取り、上流資格情報の復号を検証する。
6. Virtual Key の権限を検証する。
7. Ask、Plan、Agent、ツール呼び出し、ファイル編集、ストリーミング出力を検証する。
8. 検証してから本番環境を更新する。

本番は `litellm/Dockerfile` の固定バージョンに釘付けします。LiteLLM の `/cursor`、Responses ブリッジ、パラメータ変換、Admin UI の挙動は、バージョンで変わることがあります。

## 11. 既知の問題と切り分け

### 11.1 Rainyun が `Bad Gateway` または `no available server` を返す

意味：HTTPS サイトはできているが、コンテナの `4000` ポートの先に使える LiteLLM プロセスが無い。

対処：

1. 初回起動では LiteLLM に `2 vCPU`、`2048 MB` を与える。
2. Command と Args は空のままにする。
3. 3 つのプレースホルダキーがすべて置換済みか確認する。
4. `DATABASE_URL` に `${rca_svc_db_postgres}` が残っているか確認する。
5. データベースパスワードと `POSTGRES_PASSWORD` が完全一致か確認する。
6. `db` コンテナ名、`postgres` サービス名、`5432` ポートを確認する。
7. LiteLLM ログの Prisma migration エラーを見る。
8. 先に `/health/liveliness`、次に `/health/readiness` を確認する。

LiteLLM にログがまったく無い場合は、コンテナコマンドが Rainyun のフォームで上書きされていないか、起動できるメモリがあるかを優先して確認してください。

### 11.2 PostgreSQL に locale または `trust` 警告が出る

`postgres:16-alpine` は musl を使うため、次が出ることがあります。

```text
locale: not found
no usable system locales were found
```

初期化中に、ローカル Unix Socket が `trust` を使う旨の表示も出ることがあります。ログの最後に次が出れば問題ありません。

```text
database system is ready to accept connections
```

これでデータベースは準備完了です。初期化中に一時起動、停止、再度の正式起動があるのは通常の流れです。

### 11.3 LiteLLM が再起動し続ける

確認項目：

- `DATABASE_URL` が正しいか
- `${rca_svc_db_postgres}` が残っているか
- データベースパスワードが一致しているか
- `LITELLM_MASTER_KEY` と `LITELLM_SALT_KEY` が空でなく、`sk-` で始まっているか
- PostgreSQL が準備済みか
- Prisma migration が失敗していないか
- メモリで OOM が起きていないか

### 11.4 管理 UI にログインできない

ローカルでは `UI_USERNAME` / `UI_PASSWORD` を使います。Rainyun テンプレートでこの 2 つを設定していない場合、ユーザー名の既定は `admin`、パスワードは `LITELLM_MASTER_KEY` です。Master Key または UI パスワードを変えたら LiteLLM を再起動してください。Virtual Key は API 専用です。

### 11.5 モデル追加後に呼び出しが失敗する

次の順で確認してください。

1. API Base が正しい API ルートアドレスか
2. LiteLLM Model Name に正しいプロバイダ接頭辞があるか
3. 上流の実際のモデル名が存在するか
4. 上流 API Key が有効か
5. 上流が Chat Completions と Responses のどちらをサポートするか
6. Playground の対象 Endpoint Type が Cursor の経路と一致するか
7. Virtual Key がその Public Model Name を許可しているか

先に管理 UI の Playground で試し、そのあと Cursor を試してください。

### 11.6 Cursor が `403 Your request was blocked` を返す

LiteLLM のエラーに同時に次が出る場合：

```text
OpenAIException - Your request was blocked
Received Model Group=...
Available Model Group Fallbacks=None
```

これは、LiteLLM が出した Chat Completions リクエストを上流が拒否していることが多いです。

上流の `/v1/responses` が使え、`/v1/chat/completions` が拒否されることを確認したら、LiteLLM Model Name を次に変えてください。

```text
openai/responses/上流の実際のモデル名
```

Public Model Name はそのままにし、Playground で `/v1/chat/completions` を再テストします。

### 11.7 Playground の Responses テストは成功するが、Cursor が失敗する

原因：Playground が `/v1/responses` を直接試しており、Cursor の Chat Completions 入口をカバーしていない。

解決：Playground で明示的に `/v1/chat/completions` を選ぶ。Responses-only 上流では内部モデル名に `openai/responses/` を使う。

### 11.8 通常対話は成功するが、Agent ツールが失敗する

通常対話では次をカバーしません。

- Tool schema 変換
- Tool call ストリーミングイベント
- 複数ターンの Tool result
- 並列ツール呼び出し
- ファイル編集
- ターミナル呼び出し

第 9 節の能力完全検証を実行してください。失敗したら、LiteLLM Logs で Request ID からリクエストパラメータと上流エラーを確認します。

### 11.9 `Available Model Group Fallbacks=None`

これは、対象 Model Group に使える fallback が設定されていないことを示します。本当の原因は、同じエラー内の上流ステータスコードとメッセージ側にあることが多いです。

個人の単一上流デプロイでは fallback は不要です。高可用性が必要なら、同じ Public Model Name に複数の利用可能デプロイを足すか、明示的に fallback を設定し、プロトコル互換性をそれぞれ検証してください。

### 11.10 Cursor Base URL の指定が違う

このプロジェクトでは次を使います。

```text
https://your-domain/cursor
```

`/cursor` の `307` リダイレクトと、未認証 `/cursor/` の `401` はどちらも正常です。

### 11.11 Virtual Key にモデルへの権限が無い

Virtual Key の Models 一覧に対象の Public Model Name があるか確認してください。Cursor に記入するのは Public Model Name です。

### 11.12 再構築後にデータが消える

`db` に永続マウントがあるか確認してください。

```text
/var/lib/postgresql/data
```

Docker Volume と、Rainyun 共有ディスク上の対応サブパスを残してください。

### 11.13 Salt Key を変えたあと、上流資格情報が無効になる

Salt Key はデータベース内の上流資格情報の暗号化に使います。元の Salt Key を戻すか、すべての上流 API Key を再入力してください。新しい Salt Key では古いデータを復号できません。

### 11.14 メモリ不足または頻繁な再起動

対処：

- LiteLLM を `1536-2048 MB` に上げる
- プロジェクト全体のメモリを少なくとも `2 GB` に保つ
- `--num_workers 1` のままにする
- 個人展開では LiteLLM レプリカを 1 つだけ動かす
- 初回移行が終わってから、リソース削減を試す

### 11.15 Rainyun の Compose 取り込みが環境変数不足を出す

Rainyun の取り込み段階では、任意の入れ子 `${VAR}` を解決できません。リポジトリ同梱の `rainyun-compose.yml` を使い、プラットフォームが要求する `${rca_svc_db_postgres}` だけ残し、残りのキーは先にプレースホルダを入れて取り込み画面で置換してください。

### 11.16 GHCR イメージの取得に失敗する

確認：

- イメージ名が `ghcr.io/ninthless/llm-gateway-lite:latest` か
- GitHub Packages がそのイメージの公開匿名取得を許可しているか
- Rainyun ノードが GHCR に到達できるか
- イメージ構築ワークフローが対象アーキテクチャを公開済みか

### 11.17 モデルを変えても設定が更新されない

モデル詳細で次を確認してください。

- 上部の `LiteLLM Model` が新しい値になっている
- `LiteLLM Params` の `model` が新しい値になっている
- ページに保存成功の表示が出ている

そのあと Playground に戻り、モデルを選び直してください。必要ならモデル一覧を更新します。

### 11.18 ログの Request ID

Cursor がエラーを出したら、完全なエラーと Request ID を残してください。LiteLLM `Logs` で時刻、モデル、ステータスコードから対応リクエストを特定します。API Key、Authorization Header、完全な資格情報は非公開チャネルだけに置いてください。

### 11.19 OrangeCC が Cloudflare `502 Bad gateway` を返す

エラー本文に次が含まれる場合：

```text
orangecc.cc | 502: Bad gateway
Cloudflare
api.orangecc.cc
```

これは、LiteLLM が OrangeCC までリクエストを送ったが、OrangeCC の Cloudflare からオリジンへの間で正常応答が無かったことを示します。先にモデルプロトコルを照合してください。

- GPT / Grok：`openai/responses/...` と上流 `/v1/responses`
- Claude：`anthropic/claude-*` と OrangeCC Anthropic チャネル

Claude の現行設定：

```text
LiteLLM Model Name：anthropic/claude-sonnet-5
API Base：https://api.orangecc.cc
```

同じクラウド環境で再測し、時刻、モデル、Request ID を記録してください。直結でも LiteLLM 経由でも Cloudflare 502 なら、上流へ連絡するか、上流の復旧を待ってください。

### 11.20 Request Logs に `openai` または `anthropic` と出る

Request Logs の Provider は LiteLLM Model Name の接頭辞で決まります。

```text
openai/responses/grok-4.6  → openai
anthropic/claude-sonnet-5  → anthropic
```

Request Logs の `openai` は、LiteLLM が OpenAI Responses アダプタを選んだことを示します。行き先は設定した API Base のままです。Claude では `anthropic/claude-*` を使います。

## 12. セキュリティチェックリスト

- 公開網には LiteLLM `4000` サービスだけを出し、HTTPS サイトプロキシ経由にする
- PostgreSQL `5432` は内部アクセスのみ
- Rainyun サイトプロキシは LiteLLM の `api:4000` を指す
- Cursor には権限を絞った Virtual Key だけを使い、モデル範囲、予算、レート制限を設定する
- Master Key と Salt Key はゲートウェイ専用
- `.env` は手元または展開プラットフォームに置く
- Salt Key は資格情報を暗号化したあと変更しない
- データベースボリュームと 3 つのキーを定期バックアップする
- 上流または Virtual Key が漏れたらすぐに失効させる
- アップグレード前にテスト環境で完全な Agent ツールチェーンを検証する
- 本番アップグレード前に GHCR イメージ構築の成功を確認し、直前バージョンのロールバック情報を残す

## 13. プロジェクトの確認コマンド

```sh
node tests/check-static.mjs
docker compose config --quiet
docker compose -f rainyun-compose.yml config --no-interpolate --quiet
docker build -t llm-gateway-lite ./litellm
```

実行状態：

```sh
docker compose ps
docker compose logs -f litellm
docker compose logs -f db
```

## 14. 資料ソース

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
- [LiteLLM Proxy Configs：NO_DOCS / NO_REDOC](https://docs.litellm.ai/docs/proxy/configs)
- [Rainyun 紹介入口](https://www.rainyun.com/Nzc5MDEw_)
- [Rainyun クラウドアプリ Docker Compose 更新お知らせ](https://forum.rainyun.com/t/topic/12843)
- [Rainyun App バージョン作成チュートリアル](https://forum.rainyun.com/t/topic/11296)
- [Rainyun クラウドアプリ クイックスタート](https://www.rainyun.com/docs/products/rca/start.html)
- [Rainyun アプリ管理](https://www.rainyun.com/docs/products/rca/project/apps.html)
