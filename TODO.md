# Future work

## Automate Helm chart version updates with Flux

### Goal

Publish Helm charts as OCI artifacts in GitHub Container Registry (GHCR), detect new chart versions with Flux, and commit the selected version to an environment-specific overlay in `sandbox-cluster-config`.

Expected development flow:

```text
Publish chart 0.1.3 to GHCR
-> Flux detects tag 0.1.3
-> ImagePolicy selects 0.1.3
-> ImageUpdateAutomation updates the dev overlay
-> Flux commits and pushes the change
-> HelmRelease deploys chart 0.1.3
```

### 1. Publish the chart to GHCR

- [ ] Add a GitHub Actions workflow to `sandbox-helm-charts`.
- [ ] Trigger the workflow when `charts/sandbox-ai-consumer/**` changes on the selected release branch.
- [ ] Grant the workflow `contents: read` and `packages: write` permissions.
- [ ] Run `helm lint charts/sandbox-ai-consumer` before publishing.
- [ ] Package the chart with `helm package`.
- [ ] Log in to `ghcr.io` with `${{ github.token }}`.
- [ ] Push the package to `oci://ghcr.io/robertkustra/charts`.
- [ ] Require every release to increment `charts/sandbox-ai-consumer/Chart.yaml` `version`.
- [ ] Confirm that the resulting artifact is available as `ghcr.io/robertkustra/charts/sandbox-ai-consumer:<version>`.

### 2. Configure registry credentials

- [ ] Decide whether the GHCR chart package will be public or private.
- [ ] For a private package, ensure `ghcr-pull-secret` exists in the `flux-system` namespace.
- [ ] Give its token `read:packages` permission.
- [ ] Manage the secret outside plain Git, preferably with SOPS or another secret-management solution.

### 3. Add the OCI chart source

- [ ] Add an OCI `HelmRepository` for `oci://ghcr.io/robertkustra/charts` under `sources/`.
- [ ] Reference `ghcr-pull-secret` when the package is private.
- [ ] Keep the current `sandbox-helm-charts` Git source until all consumers have migrated.
- [ ] Verify that Flux can list and fetch the published chart version.

Target source shape:

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: sandbox-charts-oci
  namespace: flux-system
spec:
  type: oci
  interval: 5m
  url: oci://ghcr.io/robertkustra/charts
  secretRef:
    name: ghcr-pull-secret
```

### 4. Migrate the HelmRelease to OCI

- [ ] Change `apps/sandbox-ai-consumer/base/helmrelease.yaml` to use the OCI `HelmRepository`.
- [ ] Change the chart name from `charts/sandbox-ai-consumer` to `sandbox-ai-consumer`.
- [ ] Keep an exact chart version in the base as a safe fallback.
- [ ] Render the base and overlays locally after changing the source.

Target chart reference:

```yaml
chart:
  spec:
    chart: sandbox-ai-consumer
    version: "0.1.2"
    sourceRef:
      kind: HelmRepository
      name: sandbox-charts-oci
      namespace: flux-system
```

### 5. Move the managed version to the dev overlay

- [ ] Add `apps/sandbox-ai-consumer/overlays/dev/chart-version.yaml` as a HelmRelease patch.
- [ ] Add the Flux image-policy setter to `spec.chart.spec.version`.
- [ ] Reference the patch from the dev overlay `kustomization.yaml`.
- [ ] Do not duplicate the complete HelmRelease in the overlay.

Target patch:

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: sandbox-ai-consumer
spec:
  chart:
    spec:
      version: "0.1.2" # {"$imagepolicy": "flux-system:sandbox-ai-consumer-chart-dev:tag"}
```

### 6. Detect chart versions in GHCR

- [ ] Add a dedicated `ImageRepository` for `ghcr.io/robertkustra/charts/sandbox-ai-consumer`.
- [ ] Add a dedicated `ImagePolicy` named `sandbox-ai-consumer-chart-dev`.
- [ ] Apply a label to the policy so chart automation can select only chart policies.
- [ ] Restrict development updates to the intended SemVer range, for example `>=0.1.0 <0.2.0`.
- [ ] Confirm that the controller reports the newest chart tag in `ImagePolicy.status.latestRef.tag`.

### 7. Commit chart updates to the cluster repository

- [ ] Add a separate `ImageUpdateAutomation` for `sandbox-cluster-config`.
- [ ] Set `sourceRef` to the active cluster-config `GitRepository`.
- [ ] Limit `policySelector` to the chart-policy label.
- [ ] Limit `update.path` to `./apps/sandbox-ai-consumer/overlays/dev`.
- [ ] Configure checkout and push to the branch reconciled by the cluster.
- [ ] Resolve the current branch mismatch before enabling automation: active Flux sync and planned automation must use the same intended branch.
- [ ] Ensure the SSH deploy key or GitHub App used by Flux has write access to `sandbox-cluster-config`.
- [ ] Use a clear commit message such as `chore(dev): update Helm chart versions`.
- [ ] Keep this automation separate from the existing automation that writes image tags to `sandbox-env-values`.

### 8. Promotion policy

- [ ] Enable direct automatic chart updates only for `dev` initially.
- [ ] Keep `test` manual until the development workflow is proven stable.
- [ ] Promote chart versions to `prod` through a reviewed pull request or another explicitly approved process.
- [ ] Define separate SemVer ranges for each environment before enabling more automation.
- [ ] Document rollback as reverting the version commit in the environment overlay.

### 9. Validation

- [ ] Validate the chart with `helm lint sandbox-helm-charts/charts/sandbox-ai-consumer`.
- [ ] Render the app overlay with `kustomize build sandbox-cluster-config/apps/sandbox-ai-consumer/overlays/dev`.
- [ ] Render the cluster entrypoint with `kustomize build sandbox-cluster-config/clusters/minikube`.
- [ ] Reconcile the main Flux source and Kustomization.
- [ ] Verify `ImageRepository`, `ImagePolicy`, and `ImageUpdateAutomation` readiness.
- [ ] Publish a new patch chart version, for example `0.1.3`.
- [ ] Confirm that Flux commits `0.1.2 -> 0.1.3` only in the dev overlay.
- [ ] Confirm that the dev HelmRelease becomes ready with chart `0.1.3`.
- [ ] Confirm that image-tag automation in `sandbox-env-values` continues to work independently.

Useful verification commands:

```bash
flux get image repository -n flux-system
flux get image policy -n flux-system
flux get image update -n flux-system
flux get helmreleases -A
flux describe helmrelease sandbox-ai-consumer -n dev
```

### Completion criteria

- A new chart version is published to GHCR as an immutable OCI artifact.
- Flux detects the version within the configured interval.
- Flux creates a Git commit that changes only the development chart-version overlay.
- The cluster reconciles that commit and deploys the selected chart version.
- Production cannot be upgraded without the chosen approval mechanism.