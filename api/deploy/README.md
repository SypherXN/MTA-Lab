# MTA-Lab API deployment assets

## Quick install (OCI VM)

```bash
cd ~/MTA-Lab/api
chmod +x deploy/install.sh scripts/*.sh scripts/*.py
./deploy/install.sh
```

## systemd

```bash
sudo cp deploy/mta-lab-api.service.example /etc/systemd/system/mta-lab-api.service
# Edit paths if not /home/opc/MTA-Lab
sudo systemctl daemon-reload
sudo systemctl enable --now mta-lab-api
sudo systemctl status mta-lab-api
```

## nginx + TLS

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/conf.d/mta-lab-api.conf
# Edit server_name, then:
sudo certbot --nginx -d your-api.example.com
sudo nginx -t && sudo systemctl reload nginx
```

## Cron jobs

Daily backup (`deploy/backup.cron.example` pattern):

```bash
0 3 * * * /home/opc/MTA-Lab/api/scripts/backup-db.sh >> /home/opc/MTA-Lab/api/data/backup.log 2>&1
```

Intraday price watcher — see `deploy/price-watcher.cron.example`. The watcher imports quotes and fires `price-alert` webhooks when moves exceed `MTA_WATCHER_PCT_THRESHOLD`.

## Reconciliation alerts

Set in `.env`:

```
MTA_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/...
MTA_ALERT_COOLDOWN_MINUTES=60
```

Alerts fire automatically after Robinhood order import when mismatches exist, or manually:

```bash
curl -X POST https://your-api.example.com/api/admin/alerts/reconciliation-check \
  -H "X-API-Key: YOUR_WRITE_KEY"
```
