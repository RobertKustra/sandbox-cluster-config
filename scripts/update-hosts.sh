#!/usr/bin/env bash
# update-hosts.sh — synchronizes /etc/hosts with Minikube sandbox Ingress hosts.
#
# Usage:
#   sudo ./update-hosts.sh           # update /etc/hosts
#   ./update-hosts.sh --dry-run      # preview changes without modifying the file
#   ./update-hosts.sh --remove       # remove all sandbox entries from /etc/hosts
#
# The script wraps managed entries between marker comments so it is
# safe to run repeatedly — existing sandbox entries are replaced, not appended.

set -euo pipefail

HOSTS_FILE="/etc/hosts"
MARKER_START="# sandbox-cluster-hosts-start"
MARKER_END="# sandbox-cluster-hosts-end"

DRY_RUN=false
REMOVE=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --remove)  REMOVE=true  ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve Minikube IP
# ---------------------------------------------------------------------------
MINIKUBE_BIN=""

if command -v minikube &>/dev/null; then
  MINIKUBE_BIN="$(command -v minikube)"
elif [[ -n "${SUDO_USER:-}" ]]; then
  # When running with sudo, root's PATH may not include user-level binaries.
  USER_MINIKUBE_BIN=$(su - "$SUDO_USER" -c 'command -v minikube' 2>/dev/null || true)
  if [[ -n "$USER_MINIKUBE_BIN" ]]; then
    MINIKUBE_BIN="$USER_MINIKUBE_BIN"
  fi
fi

if [[ -z "$MINIKUBE_BIN" ]]; then
  echo "ERROR: minikube not found in PATH" >&2
  echo "Hint: if minikube is installed for your user, run: sudo env \"PATH=$PATH\" ./update-hosts.sh" >&2
  exit 1
fi

if [[ -n "${SUDO_USER:-}" ]]; then
  # Ensure minikube uses the invoking user's profiles/config, not root's.
  MINIKUBE_IP=$(su - "$SUDO_USER" -c "'$MINIKUBE_BIN' ip" 2>/dev/null || true)
else
  MINIKUBE_IP=$($MINIKUBE_BIN ip 2>/dev/null || true)
fi

if [[ -z "$MINIKUBE_IP" ]]; then
  echo "ERROR: could not retrieve Minikube IP. Is the cluster running?" >&2
  exit 1
fi

if [[ ! "$MINIKUBE_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "ERROR: minikube returned an invalid IP value: $MINIKUBE_IP" >&2
  echo "Hint: run 'minikube ip' manually and verify your active profile." >&2
  exit 1
fi

echo "Minikube IP: $MINIKUBE_IP"

# ---------------------------------------------------------------------------
# Static host list — add / remove entries here as Ingresses change
# ---------------------------------------------------------------------------
SANDBOX_HOSTS=(
  "sandbox-nginx.dev.local"
  "sandbox-nginx.test.local"
  "sandbox-nginx.prod.local"
  "sandbox-vllm.llm.local"
  "grafana.monitoring.local"
  "alertmanager.monitoring.local"
  "jaeger.monitoring.local"
)

# ---------------------------------------------------------------------------
# Build the new block
# ---------------------------------------------------------------------------
NEW_BLOCK="$MARKER_START"$'\n'
for host in "${SANDBOX_HOSTS[@]}"; do
  NEW_BLOCK+="$MINIKUBE_IP $host"$'\n'
done
NEW_BLOCK+="$MARKER_END"

# ---------------------------------------------------------------------------
# Dry-run — just print
# ---------------------------------------------------------------------------
if $DRY_RUN; then
  echo ""
  echo "--- entries that would be written to $HOSTS_FILE ---"
  echo "$NEW_BLOCK"
  exit 0
fi

# ---------------------------------------------------------------------------
# Check write permission
# ---------------------------------------------------------------------------
if [[ ! -w "$HOSTS_FILE" ]]; then
  echo "ERROR: $HOSTS_FILE is not writable. Run with sudo." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Remove mode — strip the managed block and exit
# ---------------------------------------------------------------------------
if $REMOVE; then
  if grep -q "$MARKER_START" "$HOSTS_FILE"; then
    # Delete lines from marker start to marker end (inclusive)
    sed -i "/$MARKER_START/,/$MARKER_END/d" "$HOSTS_FILE"
    echo "Removed sandbox entries from $HOSTS_FILE"
  else
    echo "No sandbox entries found in $HOSTS_FILE — nothing to remove."
  fi
  exit 0
fi

# ---------------------------------------------------------------------------
# Update — replace existing block or append a new one
# ---------------------------------------------------------------------------
if grep -q "$MARKER_START" "$HOSTS_FILE"; then
  # Replace the existing managed block in-place
  # Use a temp file then copy into the existing file to preserve permissions.
  TMP=$(mktemp)
  awk -v new_block="$NEW_BLOCK" \
      -v start="$MARKER_START" \
      -v end="$MARKER_END" \
      'found_start && !found_end { if ($0 ~ end) { print new_block; found_end=1 } next }
       $0 ~ start { found_start=1; next }
       { print }' "$HOSTS_FILE" > "$TMP"
  cat "$TMP" > "$HOSTS_FILE"
  rm -f "$TMP"
  echo "Updated sandbox entries in $HOSTS_FILE"
else
  # Append the block for the first time
  printf '\n%s\n' "$NEW_BLOCK" >> "$HOSTS_FILE"
  echo "Added sandbox entries to $HOSTS_FILE"
fi

echo ""
echo "Active entries:"
grep -A "${#SANDBOX_HOSTS[@]}" "$MARKER_START" "$HOSTS_FILE" | grep -v "^#"
