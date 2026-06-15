# LIVE Advanced Monitor Design

Written: 2026-06-03

## Features

1. Three-level alert visual engine (normal/warning/fault)
2. Configurable info watermarks on devices
3. Simple health score (uptime 40% + efficiency 30% + fault 30%)
4. Bottom ticker bar for alerts
5. Kiosk/fullscreen mode via button toggle

## API Changes

- Extend GET /api/workshop/3d-status with output/quality/efficiency/order/health fields
- New GET /api/alerts/ticker for recent alert messages

## Files

- app.py: extend 3d-status + new ticker API
- templates/index.html: watermarks, ticker, kiosk mode, alert pulse CSS
- utils/db.py: queries for output/quality/alerts
