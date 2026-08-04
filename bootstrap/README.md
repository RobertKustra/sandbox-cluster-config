# Bootstrap assets

This directory contains optional bootstrap assets and templates used during initial Flux setup.

## Purpose

- Keep reference manifests that can help with manual or repeated Flux bootstrap workflows.
- Separate bootstrap-only files from the active cluster reconciliation entrypoint.

## What is active in this repository

- Active Minikube Flux entrypoint: `clusters/minikube/flux-system`
- Bootstrap template location: `bootstrap/flux-system-template`

The bootstrap templates are not part of the default Minikube reconciliation path unless explicitly referenced.
