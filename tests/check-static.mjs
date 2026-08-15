import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const [compose, rainyunCompose, dockerfile, config] = await Promise.all([
  readFile("docker-compose.yml", "utf8"),
  readFile("rainyun-compose.yml", "utf8"),
  readFile("litellm/Dockerfile", "utf8"),
  readFile("litellm/config.yaml", "utf8"),
]);

assert.match(compose, /litellm:\s+build: \.\/litellm/);
assert.match(compose, /postgres:16-alpine/);
assert.match(compose, /"3029:4000"/);
assert.doesNotMatch(compose, /^\s{2}web:/m);
assert.match(rainyunCompose, /ghcr\.io\/ninthless\/api2cursor-next-litellm:latest/);
assert.match(
  rainyunCompose,
  /litellm:\s+image: ghcr\.io\/ninthless\/api2cursor-next-litellm:latest\s+pull_policy: always/,
);
assert.match(rainyunCompose, /\$\{rca_svc_db_postgres\}/);
assert.match(rainyunCompose, /postgres_data:\/var\/lib\/postgresql\/data/);
assert.match(rainyunCompose, /"4000:4000"/);
assert.doesNotMatch(rainyunCompose, /api2cursor-next-web/);
assert.doesNotMatch(rainyunCompose, /^\s+deploy:/m);
assert.doesNotMatch(rainyunCompose, /\$\{(?:POSTGRES_PASSWORD|LITELLM_MASTER_KEY|LITELLM_SALT_KEY|PUBLIC_BASE_URL)\}/);
assert.match(rainyunCompose, /LITELLM_MASTER_KEY: sk-replace-with-random-master-key/);
assert.match(rainyunCompose, /LITELLM_SALT_KEY: sk-replace-with-random-salt-key/);
assert.doesNotMatch(rainyunCompose, /PROXY_BASE_URL/);
assert.equal(
  rainyunCompose.match(/replace-with-random-postgres-password/g)?.length,
  2,
);
assert.match(dockerfile, /litellm-database:v1\.97\.0-rc\.1/);
assert.match(dockerfile, /"--num_workers", "1"/);
assert.match(config, /store_model_in_db: true/);

console.log("Static contracts passed");
