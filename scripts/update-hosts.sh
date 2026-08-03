#!/usr/bin/env bash
# update-hosts.sh - synchronizes /etc/hosts with Minikube sandbox Ingress hosts.
#
# Usage:
#   sudo ./update-hosts.sh           # update /etc/hosts
#   sudo ./update-hosts.sh --windows # update /etc/hosts and Windows hosts (WSL)
#   ./update-hosts.sh --dry-run      # preview changes without modifying the file
#   ./update-hosts.sh --remove       # remove all sandbox entries from /etc/hosts
#
# The script wraps managed entries between marker comments so it is
# safe to run repeatedly - existing sandbox entries are replaced, not appended.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOSTS_FILE="/etc/hosts"
WINDOWS_HOSTS_FILE="/mnt/c/Windows/System32/drivers/etc/hosts"
MARKER_START="# sandbox-cluster-hosts-start"
MARKER_END="# sandbox-cluster-hosts-end"

DRY_RUN=false
REMOVE=false
UPDATE_WINDOWS=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --remove)  REMOVE=true  ;;
    --windows) UPDATE_WINDOWS=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve Minikube IP
# ---------------------------------------------------------------------------
MINIKUBE_BIN=""
POWERSHELL_BIN=""

if command -v minikube &>/dev/null; then
  MINIKUBE_BIN="$(command -v minikube)"
elif [[ -n "${SUDO_USER:-}" ]]; then
  # When running with sudo, root's PATH may not include user-level binaries.
  USER_MINIKUBE_BIN=$(su - "$SUDO_USER" -c 'command -v minikube' 2>/dev/null || true)
  if [[ -n "$USER_MINIKUBE_BIN" ]]; then
    MINIKUBE_BIN="$USER_MINIKUBE_BIN"
  fi
fi

if command -v powershell.exe &>/dev/null; then
  POWERSHELL_BIN="$(command -v powershell.exe)"
elif [[ -x "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe" ]]; then
  POWERSHELL_BIN="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
elif [[ -n "${SUDO_USER:-}" ]]; then
  USER_POWERSHELL_BIN=$(su - "$SUDO_USER" -c 'command -v powershell.exe' 2>/dev/null || true)
  if [[ -n "$USER_POWERSHELL_BIN" ]]; then
    POWERSHELL_BIN="$USER_POWERSHELL_BIN"
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
# Static host list - add / remove entries here as Ingresses change
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

TARGET_HOSTS_FILES=("$HOSTS_FILE")
if $UPDATE_WINDOWS; then
  if [[ ! -f "$WINDOWS_HOSTS_FILE" ]]; then
    echo "ERROR: Windows hosts file not found at $WINDOWS_HOSTS_FILE" >&2
    exit 1
  fi
  TARGET_HOSTS_FILES+=("$WINDOWS_HOSTS_FILE")
fi

run_windows_hosts_update() {
  local helper_ps1
  local helper_win_path

  helper_ps1="$SCRIPT_DIR/update-hosts-windows.ps1"
  if [[ -z "$POWERSHELL_BIN" ]] || ! command -v wslpath &>/dev/null || [[ ! -f "$helper_ps1" ]]; then
    echo "ERROR: Windows update helper is not available." >&2
    echo "Hint: run scripts/update-hosts-windows.ps1 in an elevated PowerShell window." >&2
    exit 1
  fi

  helper_win_path="$(wslpath -w "$helper_ps1")"

  if $DRY_RUN; then
    "$POWERSHELL_BIN" -NoProfile -ExecutionPolicy Bypass -File "$helper_win_path" -MinikubeIp "$MINIKUBE_IP" -DryRun
    return
  fi

  if $REMOVE; then
    if "$POWERSHELL_BIN" -NoProfile -ExecutionPolicy Bypass -File "$helper_win_path" -Remove >/dev/null 2>&1; then
      return
    fi
  else
    if "$POWERSHELL_BIN" -NoProfile -ExecutionPolicy Bypass -File "$helper_win_path" -MinikubeIp "$MINIKUBE_IP" >/dev/null 2>&1; then
      return
    fi
  fi

  local ps_remove_arg=""
  if $REMOVE; then
    ps_remove_arg=",'-Remove'"
  else
    ps_remove_arg=",'-MinikubeIp','$MINIKUBE_IP'"
  fi

  # Fallback: request elevation via UAC when direct write to Windows hosts is denied.
  "$POWERSHELL_BIN" -NoProfile -Command "\$args = @('-NoProfile','-ExecutionPolicy','Bypass','-File','$helper_win_path'$ps_remove_arg); Start-Process -FilePath 'PowerShell' -Verb RunAs -ArgumentList \$args" >/dev/null
  echo "Requested elevated Windows hosts update via UAC prompt."
  echo "If prompted, accept the UAC dialog in Windows."
}

apply_to_hosts_file() {
  local target_file="$1"

  if [[ "$target_file" == "$WINDOWS_HOSTS_FILE" ]]; then
    run_windows_hosts_update
    return
  fi

  if $DRY_RUN; then
    echo ""
    echo "--- entries that would be written to $target_file ---"
    echo "$NEW_BLOCK"
    return
  fi

  if [[ ! -w "$target_file" ]]; then
    echo "ERROR: $target_file is not writable." >&2
    echo "Hint: run with sudo." >&2
    exit 1
  fi

  if $REMOVE; then
    if grep -q "$MARKER_START" "$target_file"; then
      sed -i "/$MARKER_START/,/$MARKER_END/d" "$target_file"
      echo "Removed sandbox entries from $target_file"
    else
      echo "No sandbox entries found in $target_file - nothing to remove."
    fi
    return
  fi

  if grep -q "$MARKER_START" "$target_file"; then
    # Replace the existing managed block while preserving file permissions.
    local tmp
    tmp=$(mktemp)
    awk -v new_block="$NEW_BLOCK" \
        -v start="$MARKER_START" \
        -v end="$MARKER_END" \
        'found_start && !found_end { if ($0 ~ end) { print new_block; found_end=1 } next }
         $0 ~ start { found_start=1; next }
         { print }' "$target_file" > "$tmp"
    cat "$tmp" > "$target_file"
    rm -f "$tmp"
    echo "Updated sandbox entries in $target_file"
  else
    printf '\n%s\n' "$NEW_BLOCK" >> "$target_file"
    echo "Added sandbox entries to $target_file"
  fi

  echo ""
  echo "Active entries in $target_file:"
  grep -A "${#SANDBOX_HOSTS[@]}" "$MARKER_START" "$target_file" | grep -v "^#"
}

for target_file in "${TARGET_HOSTS_FILES[@]}"; do
  apply_to_hosts_file "$target_file"
done
