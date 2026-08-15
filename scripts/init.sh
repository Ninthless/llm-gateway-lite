#!/usr/bin/env sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_file="$root_dir/.env"

if [ -f "$env_file" ]; then
  printf '.env already exists: %s\n' "$env_file"
  exit 0
fi

random_secret() {
  od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
}

cat > "$env_file" <<EOF
LITELLM_MASTER_KEY=sk-$(random_secret)
LITELLM_SALT_KEY=sk-$(random_secret)
POSTGRES_PASSWORD=$(random_secret)
PUBLIC_BASE_URL=http://localhost:3029
EOF

printf 'Created %s\n' "$env_file"
