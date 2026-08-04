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

Environments are isolated so changes in one environment do not affect the others directly. Each enabled environment or cluster component also owns the namespace manifest it needs.

## PostgreSQL environments

The Minikube entrypoint also deploys one `PostgresCluster` named `sandbox-postgres` into each application namespace:

- `dev`
- `test`
- `prod`

The manifests live under `postgres/overlays/<env>` and are included by the matching files in `environments/<env>/kustomization.yaml`.

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
