#!/usr/bin/env bash
set -euo pipefail

KEY_PATH="${HOME}/.ssh/id_ed25519_flux"
PUB_KEY_PATH="${KEY_PATH}.pub"

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

if [[ ! -f "${KEY_PATH}" ]]; then
  ssh-keygen -t ed25519 -C "flux@minikube" -f "${KEY_PATH}" -N ""
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required but not installed." >&2
  exit 1
fi

kubectl create namespace flux-system --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic flux-system \
  --from-file=identity="${KEY_PATH}" \
  -n flux-system \
  --dry-run=client -o yaml | kubectl apply -f -

echo
 echo "Add this public key to GitHub under Settings -> SSH and GPG keys:" 
echo
cat "${PUB_KEY_PATH}"
echo
