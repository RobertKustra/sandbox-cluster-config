# Flux Kustomizations for Minikube

Application environments and shared cluster components have separate Flux Kustomization manifests.

Environment manifests live in `clusters/minikube/environments`:

- dev.yaml for the dev environment
- test.yaml for the test environment
- prod.yaml for the prod environment

Shared cluster components live in `cluster-components`:

- monitoring.yaml for the monitoring environment
- llm.yaml for the llm environment
- clickhouse-operator.yaml for the ClickHouse operator required by Langfuse
- langfuse-namespace.yaml for the shared Langfuse namespace
- langfuse-postgres.yaml for the Crunchy-managed Langfuse database
- langfuse.yaml for the Langfuse observability platform
- traefik.yaml for the Traefik ingress controller
- operators-postgres.yaml for PostgreSQL operator resources

These manifests can be applied directly by Flux and are referenced by `clusters/minikube/kustomization.yaml`.
