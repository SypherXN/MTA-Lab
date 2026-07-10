# MTA-Lab API deployment assets

## Quick install (OCI VM)

```bash
cd ~/MTA-Lab/api
chmod +x deploy/*.sh scripts/*.sh scripts/*.py ../scripts/mta
./deploy/install.sh
# edit .env, then:
./deploy/install-service.sh    # auto-start on boot + restart on crash
./deploy/install-cron.sh       # optional maintenance cron
```

## Operator CLI (`mta-ctl`)

From the VM:

```bash
cd ~/MTA-Lab/api
./scripts/mta-ctl.sh status
./scripts/mta-ctl.sh update          # git pull + deps + sync plans + restart
./scripts/mta-ctl.sh logs -f
./scripts/mta-ctl.sh backup
./scripts/mta-ctl.sh sync-plans
```

From repo root (wrapper):

```bash
./scripts/mta status
./scripts/mta update
```

Optional symlink for convenience:

```bash
sudo ln -sf ~/MTA-Lab/scripts/mta /usr/local/bin/mta
mta status
mta update
```

### `update.sh` flags

```bash
./deploy/update.sh --no-pull         # restart only (config/plan sync local)
./deploy/update.sh --no-sync-plans   # skip plans/*.json import
./deploy/update.sh --no-restart      # pull + deps without restart
```

## systemd (auto-start)

`install-service.sh` installs `mta-lab-api.service` with:

- `Restart=always` — recovers from crashes
- `WantedBy=multi-user.target` + `enable` — starts on VM reboot

```bash
./deploy/install-service.sh
systemctl status mta-lab-api
journalctl -u mta-lab-api -f
```

Override paths:

```bash
INSTALL_DIR=/home/opc/MTA-Lab INSTALL_USER=opc ./deploy/install-service.sh
```

## nginx + TLS

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/conf.d/mta-lab-api.conf
# Edit server_name, then:
sudo certbot --nginx -d your-api.example.com
sudo nginx -t && sudo systemctl reload nginx
```

Enable nginx on boot (usually default):

```bash
sudo systemctl enable nginx
```

## Cron jobs

`install-cron.sh` adds:

- Daily backup at 03:00 UTC → `data/backup.log`
- Weekly retention at 04:00 UTC Sunday → `data/retention.log`

Manual examples in `backup.cron.example` and `retention.cron.example`.

Intraday price watcher — see `price-watcher.cron.example`.

## Deploy updates (typical)

```bash
cd ~/MTA-Lab/api
./scripts/mta-ctl.sh update
```

Or:

```bash
cd ~/MTA-Lab
git pull
./scripts/mta update
```

## Reconciliation alerts

Set in `.env`:

```
MTA_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/...
MTA_ALERT_COOLDOWN_MINUTES=60
```

```bash
curl -X POST https://your-api.example.com/api/admin/alerts/reconciliation-check \
  -H "X-API-Key: YOUR_WRITE_KEY"
```

## Dashboard (GitHub Pages)

Deploy `dashboard/` separately via GitHub Pages. Set `MTA_CORS_ORIGINS` to include your Pages URL. See [../../dashboard/README.md](../../dashboard/README.md).

## Management recommendations

| Practice | Why |
|----------|-----|
| `./deploy/install-service.sh` | Survives reboots and uvicorn crashes |
| `./deploy/install-nginx.sh` | nginx starts on boot (HTTPS front door) |
| `./deploy/secure-env.sh` | Read key + dashboard password for public API |
| `./deploy/production-hardening.sh URL` | All of the above + uptime cron |
| `./scripts/mta-ctl.sh update` manually | Never cron `git pull` — script blocks dirty tree |
| `./scripts/mta-ctl.sh install-cron --with-uptime` | Local health alerts via Slack webhook |
| External UptimeRobot on `/health` | Catches full VM/nginx outages — see `.local/uptime-external-setup.md` |
| `MTA_READ_API_KEY` + dashboard password | Lock down public dashboard |
| `journalctl -u mta-lab-api` | Central logs — no separate log files for API |
| Keep plans in git, not SCP | `sync-plans` keeps DB aligned with repo |

## Related

- [../../docs/ops-oci.md](../../docs/ops-oci.md) — full OCI notes
- [../../docs/agent-plans.md](../../docs/agent-plans.md) — plan sync
