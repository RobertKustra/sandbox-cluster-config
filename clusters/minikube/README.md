# Minikube cluster layout

This folder contains the isolated Flux entrypoints for the Minikube cluster.

## Structure

- dev/ - configuration for the dev environment
- test/ - configuration for the test environment
- prod/ - configuration for the prod environment
- environments/ - Flux Kustomization manifests per environment

Each environment is isolated so changes in one environment do not affect the others directly.

## PostgreSQL environments

The Minikube entrypoint also deploys one `PostgresCluster` named `sandbox-postgres` into each application namespace:

- `dev`
- `test`
- `prod`

The manifests live under `postgres/overlays/<env>` and are included by the matching files in `environments/<env>/kustomization.yaml`.

### Useful commands

```bash
kustomize build clusters/minikube
flux reconcile kustomization dev -n flux-system --with-source
flux reconcile kustomization test -n flux-system --with-source
flux reconcile kustomization prod -n flux-system --with-source
kubectl get postgresclusters.postgres-operator.crunchydata.com -A
kubectl get pods -n postgres-operator
```
