# sandbox-cluster-config

Flux GitOps configuration for the Sandbox cluster.

## Structure

- clusters/minikube/ - cluster-specific entrypoint for the Minikube cluster
- clusters/minikube/dev/ - isolated configuration for the dev environment
- clusters/minikube/test/ - isolated configuration for the test environment
- clusters/minikube/prod/ - isolated configuration for the prod environment
- sources/ - GitRepository definitions for the Helm charts and environment values repositories
- namespaces/dev/, namespaces/test/, namespaces/prod/ - namespace definitions per environment
- apps/dev/, apps/test/, apps/prod/ - HelmRelease definitions per environment

## Flow

1. Flux reads the GitRepository sources from this repository.
2. Each environment is isolated in its own subdirectory under the Minikube cluster folder.
3. The cluster entrypoint references dev, test, and prod independently.
4. Each HelmRelease pulls values from the matching path in the sandbox-env-values repository.

## Bootstrap commands for Minikube + Flux

## GitHub + SSH access for Flux

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
flux bootstrap github \
  --owner=RobertKustra \
  --repository=sandbox-cluster-config \
  --branch=main \
  --path=./clusters/minikube \
  --personal
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

> If you use SSH instead of HTTPS for GitHub, make sure the required GitHub deploy key or SSH secret is available in the flux-system namespace.
