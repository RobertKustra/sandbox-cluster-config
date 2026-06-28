# Flux Kustomizations for Minikube

Each environment has its own Flux Kustomization manifest:

- dev.yaml for the dev environment
- test.yaml for the test environment
- prod.yaml for the prod environment

These manifests target isolated paths under the Minikube cluster folder and can be applied directly by Flux.
