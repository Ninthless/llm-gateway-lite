#!/bin/bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SRC="${SCRIPT_DIR}/sync-cloudflare-ufw.sh"
SYNC_DST="/usr/local/sbin/sync-cloudflare-ufw.sh"
CRON_FILE="/etc/cron.weekly/sync-cloudflare-ufw"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ufw

install -m 0755 "$SYNC_SRC" "$SYNC_DST"

if ! ufw status | grep -q "Status: active"; then
  echo "abort: ufw is not active" >&2
  exit 1
fi

if ! ufw status numbered | grep -qE '22/tcp.*ALLOW'; then
  echo "abort: no ufw allow rule for 22/tcp; add ssh rule first" >&2
  exit 1
fi

echo "=== removing broad 80/443 allows (if any) ==="
while read -r num; do
  [[ -n "$num" ]] || continue
  line="$(ufw status numbered | sed -n "s/^\[\(${num}\)\].*/\0/p")"
  echo "delete: ${line}"
  ufw --force delete "$num"
done < <(
  ufw status numbered \
    | grep -E '(80|443)/tcp' \
    | grep -vF 'cloudflare-sync' \
    | grep -v '22/tcp' \
    | sed -n 's/^\[\([0-9]*\)\].*/\1/p' \
    | sort -rn
)

echo "=== syncing cloudflare ranges ==="
"$SYNC_DST"

cat >"$CRON_FILE" <<'EOF'
#!/bin/sh
/usr/local/sbin/sync-cloudflare-ufw.sh >> /var/log/sync-cloudflare-ufw.log 2>&1
EOF
chmod 0755 "$CRON_FILE"
touch /var/log/sync-cloudflare-ufw.log

echo
echo "=== ufw status (numbered) ==="
ufw status numbered

echo
echo "done: cloudflare-only 80/443 on host ufw"
echo "rainyun console should still allow 0.0.0.0/0 on 80,443 tcp and your home ip on 22"
