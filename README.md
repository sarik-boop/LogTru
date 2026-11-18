# LogTru demo

Load -> route -> fuel plan -> Telegram, with Postgres as the single source of truth.

## Deploy (on the server)
```
cd /opt/calzada && git clone https://github.com/sarik-boop/LogTru . 
cp .env.example .env && nano .env        # fill in values; never commit .env
docker compose up -d --build
```
Open http://SERVER_IP (basic auth from .env). Import prices: `POST /api/import/fills`; add loads: `POST /api/loads`.

## Status
Working: planner (fuel DP + Google routing), Postgres schema, Telegram send, dashboard.
Not built yet: QuickManage / United Fuel browser robot, Samsara feed, driver-reply handling.
