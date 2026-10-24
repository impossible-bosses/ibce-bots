# Helm chart: ibce-bots

Deploys the Docker image (`ghcr.io/impossible-bosses/ibce-bot:latest`,
built by the `go-docker` branch workflow) to a Kubernetes cluster. The
manifests previously kept in this folder (namespace/pvc/secret/
configmap/deployment yaml) are now generated from the chart.

## Install

```sh
helm install ibce-bots deploy/chart \
  --namespace ibce-bots \
  --create-namespace \
  --set params.botId=123 \
  --set params.botToken="<discord_bot_token>" \
  --set constants.comGuildId="777162167446274048" \
  --set constants.comChannelId="77706795912383437"
```

Keep the id overrides *quoted* on the command line: the Discord ids are
bigger than a 53-bit float and values.yaml keeps them as strings for the
same reason.

Values are documented in `deploy/chart/values.yaml`. The
deployment-time placeholders:

| values key | What it is |
|---|---|
| `params.botId` | Bot's COM network id (Secret, env `BOT_ID`) |
| `params.botToken` | Discord bot token (Secret, env `BOT_TOKEN`) |
| `params.rebootOnUpdate` | Leave empty (see warning in values.yaml) |
| `constants.*` | Rendered into the `constants.py` ConfigMap (guild / channel / role ids, command character) |
| `persistence.size`, `persistence.storageClassName` | PVC sizing (empty = cluster default class) |
| `imagePullSecrets.create` + `imagePullSecrets.username` / `imagePullSecrets.password` | Creates the ghcr.io docker-registry Secret from the chart (needed while the GHCR package is private; token must have `read:packages`) |
| `imagePullSecrets.names` | Alternative: reference pre-existing docker-registry Secrets instead |

## What is persisted (PVC `ibce-bots-data`)

The bot writes its state inside the application root
(`/usr/src/ibce-bots`), so the DB is mounted from the PVC with `subPath`
instead of mounting the volume over the whole app:

| Container path | PVC subPath | Content |
|---|---|---|
| `/usr/src/ibce-bots/IBCE_WARN.db` | `IBCE_WARN.db` | SQLite database (file mount - the app also moves it to `archive/` on updates) |

## Ephemeral storage (not persisted)

| Container path | Volume | Content |
|---|---|---|
| `/usr/src/ibce-bots/logs` | `emptyDir` | Rolling `.log` files |
| `/usr/src/ibce-bots/archive` | container writable layer | Last copy of the DB before an update (created by the app; dormant with a single replica) |

Wiped on every pod restart. `!get_logs` only sees the log files of the
current pod.

## Config files inside the container

- Secret `params` -> `BOT_ID`, `BOT_TOKEN`, `REBOOT_ON_UPDATE`
  (injected as environment variables, replacing the old `params.py`).
- ConfigMap `constants` -> `constants.py`, mounted read-only at
  `/usr/src/ibce-bots/constants.py`.

Caveat: the `!update_constants` Discord command writes to that file and
expects to reboot the machine; with a read-only ConfigMap mount it will
fail. Change the `constants.*` values and upgrade the release instead:

```sh
helm upgrade ibce-bots deploy/chart -n ibce-bots -f values.yaml
```

The Deployment uses `strategy: Recreate` (not RollingUpdate) since the
ReadWriteOnce PVC cannot be mounted by two pods at once.

## Updating the image

```sh
helm upgrade ibce-bots deploy/chart -n ibce-bots \
  --reuse-values --set image.tag=<new-tag-or-sha>
```
