# Kubernetes deployment of ibce-bots

Manifests to deploy the Docker image
(`ghcr.io/impossible-bosses/ibce-bot:latest`, built by the `go-docker`
branch workflow) into a Kubernetes cluster.

```sh
kubectl apply -f deploy/
```

## Before applying - populate at deployment time

| File | What to fill in |
|---|---|
| `deploy/secret.yaml` | `BOT_ID`, `BOT_TOKEN` placeholders. Leave `REBOOT_ON_UPDATE` empty (see warning in the file). |
| `deploy/configmap.yaml` | `constants.py` content: guild / channel / role ids. |
| `deploy/pvc.yaml` | `storageClassName` if your cluster needs a specific one (empty string uses the cluster default). |

## What is persisted (PVC `ibce-bots-data`)

The bot writes most of its state inside the application root
(`/usr/src/ibce-bots`), so individual paths are mounted from the PVC
with `subPath` instead of mounting the volume over the whole app:

| Container path | PVC subPath | Content |
|---|---|---|
| `/usr/src/ibce-bots/IBCE_WARN.db` | `IBCE_WARN.db` | SQLite database (file mount - the app also moves it to `archive/` on updates) |
| `/usr/src/ibce-bots/archive` | `archive` | DB archives |

## Ephemeral storage (not persisted)

| Container path | Volume | Content |
|---|---|---|
| `/usr/src/ibce-bots/logs` | `emptyDir` | Rolling `.log` files, wiped on every pod restart |

`!get_logs` only sees the log files of the current pod.

## Config

- `deploy/secret.yaml` -> `BOT_ID`, `BOT_TOKEN`, `REBOOT_ON_UPDATE`
  (injected as environment variables, replacing the old `params.py`).
- `deploy/configmap.yaml` -> `constants.py`, mounted read-only at
  `/usr/src/ibce-bots/constants.py`.

Caveat: the `!update_constants` Discord command writes to that file and
expects to reboot the machine; with a read-only ConfigMap mount it will
fail. Edit the ConfigMap and restart the pod instead:

```sh
kubectl -n ibce-bots rollout restart deployment/ibce-bots
```

## Updating

`strategy: Recreate` is intentionally used (not RollingUpdate) since the
ReadWriteOnce PVC cannot be mounted by two pods at once.

```sh
kubectl -n ibce-bots set image deployment/ibce-bots \
  ibce-bots=ghcr.io/impossible-bosses/ibce-bot:<new-tag-or-sha>
```

## Not included

- No liveness/readiness probes: the bot has no HTTP endpoint; it only
  talks to Discord.
- No Service: the bot only makes outbound connections.
