*** INFO ***
Kustomizing namespaces separately (as in this directory) is useful when you want a single, shared namespace definition—such as "dev"—reused across multiple clusters with the same annotations.

In the current Minikube flow, the `dev`, `test`, and `prod` namespaces are created by the matching `sandbox-env-values` overlays, so this directory is now intended only for shared cluster-component namespaces such as `monitoring`, `llm`, `cert-manager`, and `traefik`.

If you need cluster-specific namespace definitions instead, move them to ./clusters/<cluster-name>/environments/ and reference them directly in the kustomization, as shown below.

```
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ./namespace.yaml
  - ../../../../apps/sandbox-nginx/overlays/dev
  - ../../../../apps/sandbox-redis/overlays/dev
  - ../../../../postgres/overlays/dev
```