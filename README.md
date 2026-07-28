# sandbox-cluster-config

Flux GitOps configuration for the Sandbox cluster.

## Structure

- clusters/minikube/ - cluster-specific entrypoint for the Minikube cluster
- clusters/minikube/environments/dev/ - isolated configuration for the dev environment
- clusters/minikube/environments/test/ - isolated configuration for the test environment
- clusters/minikube/environments/prod/ - isolated configuration for the prod environment
- clusters/minikube/environments/monitoring/ - isolated configuration for the monitoring environment
- clusters/minikube/environments/llm/ - isolated configuration for the llm environment
- clusters/minikube/environments/namespaces/ - namespace bootstrap package for all environments
- sources/ - GitRepository definitions for the Helm charts and environment values repositories
- namespaces/dev/, namespaces/test/, namespaces/prod/, namespaces/llm/ - simplified namespace packages per environment
- namespaces/monitoring/ - monitoring namespace package
- apps/sandbox-ai-consumer/base/, apps/sandbox-nginx/base/, apps/sandbox-redis/base/ - per-application base packages
- apps/overlays/dev/, apps/overlays/test/, apps/overlays/prod/ - environment overlays composing per-application packages
- apps/llm/ - sandbox-vllm application package (HelmRelease + ingress)
- apps/monitoring/ - monitoring stack package for the whole cluster
- postgres/base/ - shared Crunchy PGO PostgresCluster manifest
- postgres/overlays/dev/, postgres/overlays/test/, postgres/overlays/prod/ - environment overlays for PostgreSQL instances

## Flow

1. Flux reads the GitRepository sources from this repository.
2. Each environment is isolated in its own subdirectory under the Minikube cluster folder.
3. The cluster entrypoint references dev, test, prod, monitoring, and llm independently.
4. Each HelmRelease pulls values from the matching path in the sandbox-env-values repository.

## LLM deployment

The LLM environment deploys `sandbox-vllm` from the `charts/sandbox-vllm` chart.

- HelmRelease: `apps/llm/sandbox-vllm.yaml`
- Ingress host: `sandbox-vllm.llm.local`
- Smoke test: Helm hook Job executed after install and upgrade

## Bootstrap commands for Minikube + Flux

## GitHub + SSH access for Flux

This setup uses GitHub SSH for the Flux GitRepository sources and the ongoing Git sync. The bootstrap command itself still needs a GitHub token (PAT) for the GitHub API when creating or configuring the repository, but the later Flux sync uses the SSH key stored in the flux-system secret.

Run the helper script below to generate an SSH key, create the Kubernetes secret for Flux, and print the public key that must be added to GitHub.

```bash
chmod +x scripts/setup-flux-ssh.sh
./scripts/setup-flux-ssh.sh
```

The script will print the public key at the end. Copy it and add it to GitHub under Settings → SSH and GPG keys.

### Start Minikube

```bash
minikube start
kubectl config current-context
```

### 2. Install Flux CLI

```bash
curl -s https://fluxcd.io/install.sh | sudo bash
flux --version
```

### 3. Bootstrap Flux in the cluster

```bash
export GITHUB_TOKEN=<your-github-token>

flux bootstrap github \
  --owner=RobertKustra \
  --repository=sandbox-cluster-config \
  --branch=development \
  --path=./clusters/minikube \
  --personal \
  --ssh-key-algorithm=rsa \
  --ssh-hostname=github.com
```

### 4. Verify Flux components

```bash
kubectl get pods -n flux-system
kubectl get kustomizations -A
```

### 5. Optional: check the deployed resources

```bash
kubectl get namespaces
kubectl get helmreleases -A
```

## PostgreSQL on Minikube

The Minikube cluster already includes the Crunchy Postgres Operator from `utils/operators/postgres/crunchy`. The PostgreSQL instances for `dev`, `test`, and `prod` are defined as `PostgresCluster` resources under the `postgres/overlays/<env>` paths.

### Validate manifests locally

```bash
kustomize build clusters/minikube/environments/dev
kustomize build clusters/minikube/environments/test
kustomize build clusters/minikube/environments/prod
kustomize build clusters/minikube/environments/monitoring
kustomize build clusters/minikube/environments/llm
kustomize build clusters/minikube
```

### Reconcile changes with Flux

```bash
flux reconcile source git sandbox-cluster-config -n flux-system
flux reconcile source git sandbox-helm-charts -n flux-system
flux reconcile source git sandbox-env-values -n flux-system
flux reconcile kustomization sandbox-cluster-config -n flux-system --with-source

# Optional per-environment values overlays
flux reconcile kustomization sandbox-env-values-dev -n flux-system --with-source
flux reconcile kustomization sandbox-env-values-test -n flux-system --with-source
flux reconcile kustomization sandbox-env-values-prod -n flux-system --with-source
```

### Troubleshooting when changes are not applied

Use this checklist when reconcile succeeds but workloads still use old manifests.

```bash
# 1) Verify source revisions fetched by Flux
flux get sources git -n flux-system

# 2) Verify Kustomization readiness and last applied revision
flux get kustomizations -n flux-system
flux describe kustomization sandbox-cluster-config -n flux-system

# 3) Verify HelmRelease state and chart version in use
flux get helmreleases -A
flux describe helmrelease sandbox-ai-consumer -n default

# 4) Force re-fetch and reconcile if needed
flux reconcile source git sandbox-helm-charts -n flux-system
flux reconcile source git sandbox-cluster-config -n flux-system
flux reconcile kustomization sandbox-cluster-config -n flux-system --with-source

# 5) Inspect recent controller events/logs
kubectl get events -n flux-system --sort-by=.lastTimestamp | tail -n 40
flux logs -n flux-system --since=30m
```

If a chart template changed, ensure both are updated:

- chart version in `Chart.yaml` in the chart repository
- HelmRelease `spec.chart.spec.version` in the cluster configuration repository

### Verify operator and database pods

```bash
kubectl get pods -n postgres-operator
kubectl get postgresclusters.postgres-operator.crunchydata.com -A
kubectl get pods -n dev
kubectl get pods -n test
kubectl get pods -n prod
```

### Inspect PostgreSQL details

```bash
kubectl describe postgrescluster sandbox-postgres -n dev
kubectl describe postgrescluster sandbox-postgres -n test
kubectl describe postgrescluster sandbox-postgres -n prod
kubectl get secrets -n dev | grep sandbox-postgres
kubectl get secrets -n test | grep sandbox-postgres
kubectl get secrets -n prod | grep sandbox-postgres
```

> If you use SSH instead of HTTPS for GitHub, make sure the SSH private key and GitHub known_hosts entry are present in the flux-system secret. The helper script above creates both automatically.
