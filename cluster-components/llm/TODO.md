# LLM deployment plan

## Goal
Create a clean and scalable structure for different LLM deployment variants:
- tiny
- small
- medium
- large

## Proposed structure
- llm/base/
  - kustomization.yaml
  - namespace.yaml
  - sandbox-vllm.yaml
  - sandbox-vllm-ingress.yaml
- llm/overlays/
  - tiny/
  - small/
  - medium/
  - large/

## Principles
- The base layer should contain shared vLLM configuration.
- Each overlay should override only selected values.
- Overlays should be used to adjust:
  - model selection
  - served model name
  - replica count
  - CPU / memory / GPU resources
  - model startup arguments if needed

## What should be considered
- Separate model configuration from resource configuration.
- Keep the setup compatible with Flux and Kustomize.
- Prefer patches for HelmRelease instead of duplicating the full configuration.
- Prepare a dedicated value set for each variant:
  - tiny: small model, minimal resources
  - small: medium model, moderate resources
  - medium: larger model
  - large: large model, more GPU and memory

## Initial example
Each overlay should override:
- values.model.args
- values.resources.requests
- values.resources.limits
- values.replicaCount

## Notes
- Before implementation, decide whether each overlay should use a different model or just different resource settings for the same model.
- If a model is too large for a small deployment, it may be better to limit the overlay to smaller models or require GPU support.