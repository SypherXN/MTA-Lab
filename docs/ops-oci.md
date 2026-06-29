# OCI Deployment Notes

Deploy the API to an Oracle Cloud Always Free `VM.Standard.E2.1.Micro`.

## Setup

```bash
sudo dnf install -y python3.11 python3.11-pip nginx
cd ~/MTA-Lab/api
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with production values
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Environment

- `MTA_DATABASE_PATH=/home/opc/MTA-Lab/api/data/mta_lab.db`
- `MTA_WRITE_API_KEY=<long random secret>`
- `MTA_READ_API_KEY=<optional read secret for dashboard + context GET>`
- `MTA_CORS_ORIGINS=https://your-user.github.io`
- `MTA_BACKUP_DIR=/home/opc/MTA-Lab/api/data/backups`
- `MTA_BACKUP_KEEP=14`

## TLS

Use certbot with the nginx example in `deploy/nginx.conf.example`.

## Backups

Run daily via cron:

```bash
0 3 * * * /home/opc/MTA-Lab/api/scripts/backup-db.sh >> /home/opc/MTA-Lab/api/data/backup.log 2>&1
```

Copy `data/backups/` to OCI Object Storage or another off-box location for disaster recovery.

## Uptime

Configure an external uptime monitor hitting `GET /health`. A `503` response means the API process is up but SQLite is unreachable.
