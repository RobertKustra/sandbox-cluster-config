# Minikube cluster layout

This folder contains the isolated Flux entrypoints for the Minikube cluster.

## Structure

- environments/ - Flux Kustomization manifests for application environments only
- environments/dev.yaml - Flux Kustomization for the dev environment
- environments/test.yaml - Flux Kustomization for the test environment
- environments/prod.yaml - Flux Kustomization for the prod environment
- ../../cluster-components/monitoring.yaml - Flux Kustomization for the monitoring environment
- ../../cluster-components/llm.yaml - Flux Kustomization for the llm environment
- ../../cluster-components/langfuse-namespace.yaml - Flux Kustomization for the Langfuse namespace
- ../../cluster-components/langfuse-postgres.yaml - Flux Kustomization for the Crunchy-managed Langfuse database
- ../../cluster-components/langfuse.yaml - Flux Kustomization for Langfuse
- ../../cluster-components/clickhouse-operator.yaml - Flux Kustomization for the ClickHouse operator
- ../../cluster-components/traefik.yaml - Flux Kustomization for the Traefik ingress controller
- ../../cluster-components/operators-postgres.yaml - Flux Kustomization for PostgreSQL operator resources

Environments are isolated so changes in one environment do not affect the others directly. The `sandbox-env-values-<env>` stages create the `dev`, `test`, and `prod` namespaces before the matching workload Kustomizations reconcile, while shared cluster components still own their namespace manifests locally.

## PostgreSQL environments

The Minikube entrypoint also deploys one `PostgresCluster` named `sandbox-postgres` into each application namespace:

- `dev`
- `test`
- `prod`

The manifests live under `postgres/overlays/<env>` and are included by the matching files in `environments/<env>/kustomization.yaml`.

## Persistent storage

The complete cluster with the `dev`, `test`, and `prod` environments should have at least 12 CPUs and 16 GB of RAM in total.

A smaller test profile has been verified with 5 CPUs and 6 GB of RAM. This configuration runs one application environment, such as `dev`, and uses the `tiny` LLM overlay. Treat these values as the tested minimum for this specific profile; other models or additional components may require more resources.

Single-node profile:

```bash
minikube start \
	-p minikube \
	--driver=docker \
	--container-runtime=docker \
	--gpus=all \
	--cpus=12 \
	--memory=16384mb
```

Two-node profile, with 6 CPUs and 8 GB of RAM per node:

```bash
minikube start \
	-p minikube \
	--nodes=2 \
	--driver=docker \
	--container-runtime=docker \
	--gpus=all \
	--cpus=6 \
	--memory=8192mb

kubectl label node minikube-m02 \
	sandbox.local/gpu=nvidia \
	--overwrite

kubectl patch daemonset nvidia-device-plugin-daemonset \
	-n kube-system \
	--type=merge \
	-p '{
		"spec": {
			"template": {
				"spec": {
					"nodeSelector": {
						"sandbox.local/gpu": "nvidia"
					}
				}
			}
		}
	}'
```

Persistent workloads use the Minikube CSI Hostpath driver and the `csi-hostpath-sc` StorageClass. Enable the required addons before Flux creates any PVCs for either profile:

```bash
minikube addons enable volumesnapshots -p minikube
minikube addons enable csi-hostpath-driver -p minikube

kubectl annotate storageclass standard \
	storageclass.kubernetes.io/is-default-class- \
	--overwrite

kubectl annotate storageclass csi-hostpath-sc \
	storageclass.kubernetes.io/is-default-class=true \
	--overwrite
```

Verify the driver and provisioned volumes:

```bash
kubectl get storageclass
kubectl get csinode
kubectl get pvc -A
kubectl get pv \
  -o custom-columns='NAME:.metadata.name,CLASS:.spec.storageClassName,DRIVER:.spec.csi.driver'
```

CSI Hostpath works with both single-node and multi-node Minikube profiles. Volumes remain local to the node selected during provisioning; PV node affinity keeps the consuming pod on that node. The driver does not replicate data between nodes, and `minikube delete` removes the test data.

## Environment scaffold workflow

Migration note: scaffold tooling was moved to the separate `sandbox-scaffolder` repository. For migration context and the minimal command flow, see `../README.md` section `Migration to sandbox-scaffolder`.

`clusters/minikube/kustomization.yaml` is the source of truth for which environments are active on this cluster.

Use the helper script to keep Flux `sandbox-env-values-<env>` manifests in sync with enabled environment entries:

```bash
cd ../sandbox-scaffolder
make run-sync HOST_REPOS_ROOT=/home/ziutek/sandbox/Repos
```

Apply a YAML scaffold config when each environment should install a different subset of services:

```bash
cd ../sandbox-scaffolder
make run CONFIG_FILE=/workspace/sandbox-scaffolder/cluster-config.yaml HOST_REPOS_ROOT=/home/ziutek/sandbox/Repos
```

The scaffold command will:

- create `sandbox-env-values/overlays/<env>` from template files in `templates/scaffold/env-values-overlay/`
- create `clusters/minikube/environments/<env>.yaml` from `templates/scaffold/minikube-environment.yaml`
- add a commented `./environments/<env>.yaml` entry to `clusters/minikube/kustomization.yaml`
- regenerate `clusters/minikube/flux-system/env-values-kustomizations.yaml`

The YAML-driven scaffold command additionally:

- installs or removes managed cluster components declared in the top-level `components` list
- derives `clusters/minikube/environments/<env>/kustomization.yaml` from the declared service list
- stores `ImageRepository` and `ImagePolicy` manifests in `clusters/minikube/environments/<env>/image-reflector.yaml` with resources in namespace `flux-system`
- derives Flux `healthChecks` from the selected Helm-based services only
- writes image tags from the service entries into the environment values overlays
- lets `sandbox-ai-consumer` choose `ghcr.io/robertkustra/<prefix>/sandbox-ai-consumer` through `image_repository_prefix`
- keeps `llm` available as a legacy service entry for cluster-level dependency only
- always adds a dependency on `minikube-llm` when `sandbox-ai-consumer` is installed
- enables image automation only for environments that explicitly set `image_updater: true`
- keeps `ImageUpdateAutomation` resources in `clusters/minikube/flux-system/image-automation.yaml`
- omits `ImageRepository` and `ImagePolicy` objects for services that are not installed in a given environment

To activate the new environment on Minikube, run `make run-sync` from `sandbox-scaffolder` after updating `cluster-config.yaml`.

### Useful commands

```bash
kustomize build clusters/minikube
flux reconcile kustomization minikube-dev -n flux-system --with-source
flux reconcile kustomization minikube-test -n flux-system --with-source
flux reconcile kustomization minikube-prod -n flux-system --with-source
flux reconcile kustomization minikube-traefik -n flux-system --with-source
flux reconcile kustomization minikube-clickhouse-operator -n flux-system --with-source
flux reconcile kustomization minikube-langfuse-namespace -n flux-system --with-source
flux reconcile kustomization minikube-langfuse-postgres -n flux-system --with-source
flux reconcile kustomization minikube-langfuse -n flux-system --with-source
kubectl get postgresclusters.postgres-operator.crunchydata.com -A
kubectl get pods -n postgres-operator
kubectl get pods -n langfuse
```
