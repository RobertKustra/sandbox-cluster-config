# sandbox-cluster-config

Flux GitOps configuration for the Sandbox cluster.

## Structure

- clusters/minikube/ - cluster-specific entrypoint for the Minikube cluster
- clusters/minikube/flux-system/ - active Flux manifests used by the Minikube cluster
- bootstrap/flux-system-template/ - optional bootstrap/template Flux manifests kept for reference
- clusters/minikube/environments/dev/ - isolated configuration for the dev environment
- clusters/minikube/environments/test/ - isolated configuration for the test environment
- clusters/minikube/environments/prod/ - isolated configuration for the prod environment
- cluster-components/ - shared cluster-level components (cert-manager, traefik, monitoring, llm, and operator bootstrap)
- sources/ - GitRepository definitions for the Helm charts and environment values repositories
- apps/sandbox-ai-consumer/base/, apps/sandbox-nginx/base/, apps/sandbox-redis/base/ - per-application base packages
- apps/sandbox-ai-consumer/overlays/<env>/, apps/sandbox-nginx/overlays/<env>/, apps/sandbox-redis/overlays/<env>/ - per-application overlays by environment
- cluster-components/llm/ - LLM stack package (HelmRelease + ingress)
- cluster-components/monitoring/ - monitoring stack package for the whole cluster
- postgres/base/ - shared Crunchy PGO PostgresCluster manifest
- postgres/overlays/dev/, postgres/overlays/test/, postgres/overlays/prod/ - environment overlays for PostgreSQL instances
- scripts/scaffold_envs/templates/scaffold/ - dedicated templates used to scaffold environments
- scripts/scaffold_envs/manage-env-values.py - sync and scaffold utility for Minikube environments

Note: only `clusters/minikube/flux-system` is reconciled by the cluster entrypoint. The bootstrap template is not part of the active Minikube reconcile path.

## Flow

1. Flux reads the GitRepository sources from this repository.
2. Cluster components include their own namespace manifests in their local component directories when needed.
3. The `sandbox-env-values-<env>` stages generate ConfigMaps and create the matching environment namespaces (`dev`, `test`, `prod`).
4. Environment stages (`minikube-dev`, `minikube-test`, `minikube-prod`) deploy workloads after the matching `sandbox-env-values-<env>` dependency succeeds and wait for HelmRelease health checks.
5. The cluster entrypoint references only the environments and shared components that should exist on that cluster.

## Environment scaffold and sync

`clusters/minikube/kustomization.yaml` is the source of truth for enabled Minikube environments.

Generate Flux `sandbox-env-values-<env>` manifests from currently enabled entries:

```bash
./scripts/scaffold_envs/manage-env-values.py sync
```

Scaffold a new environment from dedicated templates:

```bash
./scripts/scaffold_envs/manage-env-values.py scaffold <env>
```

Apply a YAML scaffold config that declares the cluster, environments, enabled services, service tags, and per-environment image updater:

```bash
./scripts/scaffold_envs/manage-env-values.py scaffold-config ./scripts/scaffold_envs/templates/scaffold/cluster-config.example.yaml
```

Template sources:

- `scripts/scaffold_envs/templates/scaffold/env-values-overlay/` for `sandbox-env-values/overlays/<env>`
- `scripts/scaffold_envs/templates/scaffold/minikube-environment.yaml` for `clusters/minikube/environments/<env>.yaml`
- `scripts/scaffold_envs/templates/scaffold/cluster-config.example.yaml` for the YAML input schema

Example scaffold config:

```yaml
cluster: minikube
environments:
  - name: dev
    services:
      - name: sandbox-nginx
        tag: "1.25"
      - name: sandbox-redis
        tag: "7.2.5"
      - name: postgres
    image_updater: false
  - name: prod
    services:
      - name: sandbox-nginx
        tag: "1.25"
      - name: sandbox-redis
        tag: "7.2.5"
      - name: sandbox-ai-consumer
        tag: "0.2.2"
        image_repository_prefix: prod
      - name: postgres
    image_updater: true
```

Service entry fields:

- `name`: service identifier used by the scaffold
- `tag`: image tag to write into the generated env values file
- `image_repository_prefix`: optional image path selector for services that support multiple registries or paths; for `sandbox-ai-consumer` this maps to `ghcr.io/robertkustra/<prefix>/sandbox-ai-consumer` and defaults to the environment name

The YAML-driven scaffold command will:

- update `clusters/<cluster>/environments/<env>/kustomization.yaml` from the declared service list
- update `clusters/<cluster>/environments/<env>.yaml` with health checks only for selected Helm-based services
- update `sandbox-env-values/overlays/<env>/kustomization.yaml` and `namespace.yaml`
- create missing per-service values files in `sandbox-env-values/overlays/<env>/` and update managed `image` blocks from the declared service tags
- regenerate `clusters/<cluster>/flux-system/env-values-kustomizations.yaml`
- regenerate `clusters/<cluster>/flux-system/image-automation.yaml` only for environments that enable `image_updater` and only for services that support image automation; `sandbox-ai-consumer` uses the configured `image_repository_prefix`
- add or remove the `image-automation.yaml` reference in `clusters/<cluster>/flux-system/kustomization.yaml`

The scaffold command adds a commented environment line to `clusters/minikube/kustomization.yaml`. Uncomment it when you want the environment to be reconciled on the cluster.

## LLM deployment

The LLM environment deploys `sandbox-vllm` from the `charts/sandbox-vllm` chart.

- HelmRelease: `cluster-components/llm/sandbox-vllm.yaml`
- Ingress host: `sandbox-vllm.llm.local`
- Smoke test: Helm hook Job executed after install and upgrade

## Bootstrap commands for Minikube + Flux

## GitHub + SSH access for Flux

## [Not-Ready] Secrets with SOPS + age

This repository uses Flux, so the simplest secrets workflow is to keep Kubernetes `Secret` manifests encrypted in Git with SOPS and decrypt them in-cluster with Flux.

### Why this approach
1. It works with public repositories.
2. It does not require GitHub Actions secrets as a runtime backend for the cluster.
3. It avoids the operational overhead of running Vault for a small Minikube-based GitOps setup.

### Recommended setup
1. Generate an age key pair locally.
2. Create a `sops-age` secret in the `flux-system` namespace from the private key.
3. Copy [clusters/minikube/.sops.yaml.example](clusters/minikube/.sops.yaml.example) to `clusters/minikube/.sops.yaml` and replace the placeholder recipient with your age public key.
4. Add `spec.decryption.provider: sops` and `spec.decryption.secretRef.name: sops-age` to the Flux Kustomization after the secret exists in the cluster.
5. Encrypt only `data` and `stringData` fields in Kubernetes `Secret` manifests.

### Example bootstrap

```bash
age-keygen -o age.agekey

cat age.agekey | kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=/dev/stdin
```

### Important note

Do not enable Flux decryption before the `sops-age` secret exists in the cluster. Otherwise the main Flux Kustomization will fail reconciliation.


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
  --components-extra=image-reflector-controller,image-automation-controller \
  --personal \
  --ssh-key-algorithm=rsa \
  --ssh-hostname=github.com
```

### 4. Verify Flux components

```bash
kubectl get pods -n flux-system
kubectl get kustomizations -A
```

### 4.1 Post-bootstrap quick checklist

Use this checklist right after bootstrap to catch missing Flux components (for example `ImagePolicy` CRD errors) early.

```bash
# 1) Confirm Flux controllers are running, including image automation components
kubectl get deploy -n flux-system

# 2) Confirm image toolkit CRDs exist
kubectl get crd | rg 'image.toolkit.fluxcd.io'

# 3) Confirm the flux-system Kustomization is Ready
flux get kustomizations -n flux-system
flux describe kustomization flux-system -n flux-system

# 4) Force one reconcile if bootstrap just finished
flux reconcile kustomization flux-system -n flux-system --with-source
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
kustomize build cluster-components/monitoring
kustomize build cluster-components/llm
kustomize build clusters/minikube
```

### Reconcile changes with Flux

```bash
flux reconcile source git sandbox-cluster-config -n flux-system
flux reconcile source git sandbox-helm-charts -n flux-system
flux reconcile source git sandbox-env-values -n flux-system
flux reconcile kustomization sandbox-cluster-config -n flux-system --with-source

# Core staged kustomizations
flux reconcile kustomization minikube-dev -n flux-system --with-source
flux reconcile kustomization minikube-test -n flux-system --with-source
flux reconcile kustomization minikube-prod -n flux-system --with-source

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
flux describe helmrelease sandbox-ai-consumer -n dev
flux describe helmrelease sandbox-ai-consumer -n test
flux describe helmrelease sandbox-ai-consumer -n prod

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
