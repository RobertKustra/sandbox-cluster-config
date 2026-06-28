#!/usr/bin/env bash
set -euo pipefail

KEY_PATH="${HOME}/.ssh/id_rsa_flux"
PUB_KEY_PATH="${KEY_PATH}.pub"
KNOWN_HOSTS_PATH="${HOME}/.ssh/known_hosts"

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

rm -f "${KEY_PATH}" "${PUB_KEY_PATH}" "${KNOWN_HOSTS_PATH}"
ssh-keygen -t rsa -b 4096 -C "flux@minikube" -f "${KEY_PATH}" -N ""
ssh-keyscan github.com > "${KNOWN_HOSTS_PATH}"
chmod 600 "${KNOWN_HOSTS_PATH}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required but not installed." >&2
  exit 1
fi

kubectl create namespace flux-system --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic flux-system \
  --from-file=identity="${KEY_PATH}" \
  --from-file=known_hosts="${KNOWN_HOSTS_PATH}" \
  -n flux-system \
  --dry-run=client -o yaml | kubectl apply -f -

echo
 echo "Add this public key to GitHub under Settings -> SSH and GPG keys:" 
echo
cat "${PUB_KEY_PATH}"
echo
