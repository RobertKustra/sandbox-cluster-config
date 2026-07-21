# Flux Kustomizations for Minikube

Each environment (and shared operator package) has its own Flux Kustomization manifest:

- dev.yaml for the dev environment
- test.yaml for the test environment
- prod.yaml for the prod environment
- monitoring.yaml for the monitoring environment
- llm.yaml for the llm environment
- operators-postgres.yaml for PostgreSQL operator resources

These manifests target isolated paths under the Minikube cluster folder and can be applied directly by Flux.
