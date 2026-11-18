# LogTru demo

Load -> route -> fuel plan -> Telegram, with Postgres as the single source of truth.

## Deploy (on the server)
```
cd /opt/calzada && git clone https://github.com/sarik-boop/LogTru . 
cp .env.example .env && nano .env        # fill in values; never commit .env
docker compose up -d --build
```
Open http://SERVER_IP (basic auth from .env). Import prices: `POST /api/import/fills`; add loads: `POST /api/loads`.

## Airtable link
Set `AIRTABLE_TOKEN` (read) in `.env`, open the dashboard and press **Sync from Airtable** (loads, stations, prices).

## QuickManage robot (untested against the live login)
Set `QM_USER`, `QM_PASS`, `AIRTABLE_WRITE_TOKEN`, then: `docker compose run --rm robot`. It refreshes Airtable "Active Loads".

## Status
Working: planner (fuel DP + Google routing), Postgres schema, Telegram send, dashboard.
Not built yet: United Fuel robot, Samsara feed, driver-reply handling.
