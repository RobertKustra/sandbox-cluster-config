# Minikube cluster layout

This folder contains the isolated Flux entrypoints for the Minikube cluster.

## Structure

- dev/ - configuration for the dev environment
- test/ - configuration for the test environment
- prod/ - configuration for the prod environment
- environments/ - Flux Kustomization manifests per environment

Each environment is isolated so changes in one environment do not affect the others directly.
