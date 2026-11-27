# kube-olympians

Cluster components for **olympians**, a four-node bare-metal Talos Linux cluster: zeus (control plane) and the workers ares, hades and hera. It is a port of `kube-demigods` and follows the same layout and practices, renamed for this cluster.

The nodes themselves (Talos machine configs, pod and service CIDRs, the disabled flannel and kube-proxy) live in **`../talos_olympians`**. This repo starts once `talosctl bootstrap` has finished and the nodes are up without a CNI.

```sh
make install          # or: make helm   (every component, in dependency order)
make -C <component>   # list that component's targets
```

Then, in order, run `make -C traefik postCertManager`, `make -C postgresql olympians`, `make -C harbor helm` and `make -C forgejo helm runners`.

Every target runs against the `admin@olympians` kube context, whatever the current context is (see `KUBE_CONTEXT` in `common.mk`).

**Secrets come from Bitwarden Secrets Manager** through External Secrets (`external-secrets/`): the Cloudflare DNS-01 token, the Backblaze B2 key, and the Harbor and Forgejo credentials. Install it right after cert-manager, before `make -C certificateManager olympians`. Its one bootstrap secret is the machine account token in the git-ignored `external-secrets/base/bitwarden.env`. See `external-secrets/README.md`.

See **[COMPONENTS.md](COMPONENTS.md)** for the components and versions, nodes and disks, storage classes, install order, waits, local patches to upstream and what uninstalling removes. Day-two operations are in `postgresql/README.md`, `harbor/README.md` and `forgejo/README.md`.
