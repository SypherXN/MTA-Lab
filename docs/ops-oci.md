# OCI Deployment Notes



Deploy the API to an Oracle Cloud Always Free `VM.Standard.E2.1.Micro`.



## Setup



```bash

sudo dnf install -y python3.11 python3.11-pip nginx

git clone https://github.com/your-user/MTA-Lab.git ~/MTA-Lab

cd ~/MTA-Lab/api

python3.11 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env

# edit .env with production values

./deploy/install.sh

```



Or use `./deploy/install.sh` after cloning.



## Environment



| Variable | Example | Notes |

|----------|---------|-------|

| `MTA_DATABASE_PATH` | `/home/opc/MTA-Lab/api/data/mta_lab.db` | SQLite path |

| `MTA_WRITE_API_KEY` | long random secret | Required for automation writes |

| `MTA_READ_API_KEY` | optional read secret | Locks down dashboard GET + context |

| `MTA_CORS_ORIGINS` | `https://your-user.github.io` | GitHub Pages origin |

| `MTA_DASHBOARD_PASSWORD` | optional | Dashboard login (Bearer token) |

| `MTA_BACKUP_DIR` | `.../data/backups` | Daily backup target |

| `MTA_BACKUP_KEEP` | `14` | Days of local backups |

| `MTA_SEQUENTIAL_LANES` | `true` | **Recommended** on shared micro |

| `MTA_LANE_LOCK_TTL_MINUTES` | `45` | Lock expiry if automation crashes |

| `MTA_PLANS_REPO_DIR` | (default) | Override path to `plans/` if needed |



## Sequential lanes (shared micro VM)



When the API shares an E2.1.Micro with other services, set `MTA_SEQUENTIAL_LANES=true` in `.env`. Lanes then run one at a time via an execution lock (see [multi-lane-simulation.md](automation/multi-lane-simulation.md)).



Add **1 GiB swap** if `free -h` shows 0B swap:



```bash

sudo fallocate -l 1G /swapfile

sudo chmod 600 /swapfile

sudo mkswap /swapfile

sudo swapon /swapfile

echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

```



## Deploy workflow (code + plans)



After each `git pull`:

```bash
cd ~/MTA-Lab
./scripts/mta update
# or: cd api && ./scripts/mta-ctl.sh update
```



Optional cron or deploy hook to run plan sync automatically.



## Dashboard (GitHub Pages)



1. Enable Pages on the `dashboard/` folder.

2. Set `dashboard/config.js` on the published branch:

   - `API_BASE_URL` → your HTTPS API

   - `PLANS_REPO_URL` → this repo (for plan edit links)

3. Add Pages URL to `MTA_CORS_ORIGINS`.



See [dashboard/README.md](../dashboard/README.md).



## TLS



Use certbot with the nginx example in `deploy/nginx.conf.example`.



## Backups



Run daily via cron:



```bash

0 3 * * * /home/opc/MTA-Lab/api/scripts/backup-db.sh >> /home/opc/MTA-Lab/api/data/backup.log 2>&1

```



Copy `data/backups/` to OCI Object Storage or another off-box location for disaster recovery.



## Retention



Prune old data via admin API (schedule weekly cron):



```bash

curl -X POST https://your-api.example.com/api/admin/retention/run \

  -H "X-API-Key: YOUR_WRITE_KEY" \

  -H "Content-Type: application/json" \

  -d '{"dry_run": false}'

```



Default policy (see `api/app/retention_service.py`):



| Data | Retention |

|------|-----------|

| Runs, decisions | 90 days |

| Portfolio snapshots | 180 days |

| Unlinked Cursor usage | 180 days |

| Resolved alerts | 30 days |

| Lanes, memory, orders, news | Indefinite (until manual cleanup) |

| Local backups (`MTA_BACKUP_KEEP`) | 14 days |



Steady-state SQLite size is typically **5–30 MB** with retention; backups may be larger.



## Uptime



Configure an external uptime monitor hitting `GET /health`. A `503` response means the API process is up but SQLite is unreachable.



## Related



- [api/deploy/README.md](../api/deploy/README.md) — systemd, nginx, cron

- [agent-plans.md](agent-plans.md) — plan sync after git pull

- [multi-lane-simulation.md](automation/multi-lane-simulation.md) — sequential mode


