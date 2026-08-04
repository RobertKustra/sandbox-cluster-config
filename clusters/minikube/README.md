# Minikube cluster layout

This folder contains the isolated Flux entrypoints for the Minikube cluster.

## Structure

- environments/ - Flux Kustomization manifests for application environments only
- environments/dev.yaml - Flux Kustomization for the dev environment
- environments/test.yaml - Flux Kustomization for the test environment
- environments/prod.yaml - Flux Kustomization for the prod environment
- ../../cluster-components/monitoring.yaml - Flux Kustomization for the monitoring environment
- ../../cluster-components/llm.yaml - Flux Kustomization for the llm environment
- ../../cluster-components/traefik.yaml - Flux Kustomization for the Traefik ingress controller
- ../../cluster-components/operators-postgres.yaml - Flux Kustomization for PostgreSQL operator resources

Environments are isolated so changes in one environment do not affect the others directly. The `sandbox-env-values-<env>` stages create the `dev`, `test`, and `prod` namespaces before the matching workload Kustomizations reconcile, while shared cluster components still own their namespace manifests locally.

## PostgreSQL environments

The Minikube entrypoint also deploys one `PostgresCluster` named `sandbox-postgres` into each application namespace:

- `dev`
- `test`
- `prod`

The manifests live under `postgres/overlays/<env>` and are included by the matching files in `environments/<env>/kustomization.yaml`.

## Environment scaffold workflow

`clusters/minikube/kustomization.yaml` is the source of truth for which environments are active on this cluster.

Use the helper script to keep Flux `sandbox-env-values-<env>` manifests in sync with enabled environment entries:

```bash
./scripts/manage-env-values.py sync
```

Create a new environment scaffold from dedicated templates:

```bash
./scripts/manage-env-values.py scaffold <env>
```

The scaffold command will:

- create `sandbox-env-values/overlays/<env>` from template files in `templates/scaffold/env-values-overlay/`
- create `clusters/minikube/environments/<env>.yaml` from `templates/scaffold/minikube-environment.yaml`
- add a commented `./environments/<env>.yaml` entry to `clusters/minikube/kustomization.yaml`
- regenerate `clusters/minikube/flux-system/env-values-kustomizations.yaml`

To activate the new environment on Minikube, uncomment the generated line in `clusters/minikube/kustomization.yaml` and run `./scripts/manage-env-values.py sync`.

### Useful commands

```bash
kustomize build clusters/minikube
flux reconcile kustomization minikube-dev -n flux-system --with-source
flux reconcile kustomization minikube-test -n flux-system --with-source
flux reconcile kustomization minikube-prod -n flux-system --with-source
flux reconcile kustomization minikube-traefik -n flux-system --with-source
kubectl get postgresclusters.postgres-operator.crunchydata.com -A
kubectl get pods -n postgres-operator
```
