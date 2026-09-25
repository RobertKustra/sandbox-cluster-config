# Environment Flux Kustomizations

This folder contains Flux Kustomization resources only for application environments.

Current scope: `dev`, `test`, and `prod`.

Shared cluster-level components are defined in `cluster-components/`. Namespace manifests are defined centrally in `namespaces/` and exposed through `cluster-components/namespaces.yaml`.
