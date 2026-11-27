# GPU Operator: the workers' RTX 3050s

Each worker (ares, hades, hera) has an NVIDIA GeForce RTX 3050. The pieces are split between Talos and Kubernetes:

| Layer | What | Where |
| --- | --- | --- |
| Kernel driver | NVIDIA **open** kernel modules, **LTS** branch (580.x) | Talos extension `siderolabs/nvidia-open-gpu-kernel-modules-lts` |
| Container runtime | `nvidia` containerd runtime handler | Talos extension `siderolabs/nvidia-container-toolkit-lts` |
| Module loading | `nvidia`, `nvidia_uvm`, `nvidia_drm`, `nvidia_modeset` | `../talos_olympians/gpu-worker-patch.yaml` (KernelModuleConfig) |
| Scheduling | device plugin (`nvidia.com/gpu`), GPU feature discovery, node feature discovery, validator, `nvidia` RuntimeClass | this component: NVIDIA GPU Operator chart (pinned in `Makefile`) |
| Metrics | DCGM exporter, scraped by Prometheus through its ServiceMonitor | this component |

The operator's own driver and toolkit are **disabled** (`helm/values.yaml`), because Talos provides them. Talos's NVIDIA guide requires GPU Operator v26.3.1 or newer.

| Task | Command (from `gpu-operator/`) |
| --- | --- |
| Install / upgrade | `make helm` (runs `prerequisites`: namespace, PSA `privileged`) |
| Check a GPU works | `make smoke-test` (runs `nvidia-smi` in a pod, prints it, deletes it) |
| Remove | `make uninstall-helm` (the Talos driver stays) |

## Using a GPU
```yaml
spec:
  runtimeClassName: nvidia
  containers:
    - name: app
      resources:
        limits:
          nvidia.com/gpu: 1
```
Each node has one GPU and there's no time-slicing, so at most one GPU pod per worker.

GPU metrics in Prometheus use the DCGM exporter's newer unit-suffixed names: `DCGM_FI_DEV_GPU_TEMP_CELSIUS`, `DCGM_FI_DEV_GPU_UTIL_RATIO`, `DCGM_FI_DEV_FB_USED_BYTES`, `DCGM_FI_DEV_BOARD_POWER_WATTS` and so on, not the older `DCGM_FI_DEV_GPU_TEMP`. Many grafana.com dashboards use the old names.

**On 2026-11-26** `nvidia-smi` showed each worker's GeForce RTX 3050 with 6 GiB, driver 580.196.07 and CUDA 13.0, idle at about 35–39 °C and 10 W of 70 W.

## Talos: two schematics
- **Workers:** `40b13a8d4f3202c7d7c95f0cc0fa5cecea2d480ea9f1f1dd3122395cd68f6e9d`, from `../talos_olympians/schematic-gpu-worker.yaml` (the two NVIDIA extensions).
- **zeus:** `376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba`, no extensions. It has no GPU.

Upgrade the workers with `factory.talos.dev/metal-installer/<worker schematic>:<talos version>`. The extensions are built for each Talos release, so the schematic ID stays the same and only the tag changes. Never upgrade a worker with zeus's schematic: that drops the driver.

`../talos_olympians/worker.yaml` already names the worker schematic and carries the four KernelModuleConfig documents, so a rebuilt worker comes up with the GPU working.

**Gotcha: the modules must be in the machine config before a worker boots with the extensions.** The extensions' services `ext-nvidia-cdi-gen` and `ext-nvidia-persistenced` wait for the `nvidia` modules, and Talos doesn't finish booting until they're up. On 2026-11-26, hera was upgraded to the GPU schematic before `gpu-worker-patch.yaml` was applied. It sat cordoned, logging "service ext-nvidia-cdi-gen to be up/finished", until the patch was applied; that took effect without a reboot. Ordinary Talos upgrades are fine, because the patch is already in each worker's config.
