# Yandex Weather Bridge

Private bridge: OpenWeather -> Yandex Smart Home virtual outdoor temperature sensor.

## Device

- Name: `Улица`
- Type: `devices.types.sensor.climate`
- Property: `temperature`
- Weather point: Akademicheskiy, Yekaterinburg (`56.7805, 60.5156`)

## Production layout

- `/opt/weather-bridge/source` — current source checkout
- `/opt/weather-bridge/releases` — immutable releases (`V1`, `V2`, ...)
- `/opt/weather-bridge/runtime` — neutral production runtime
- `/opt/weather-bridge/secrets` — secrets, never in Git
- `/opt/weather-bridge/data` — rootless Docker data and persistent app data
- `/opt/weather-bridge/logs` — project-specific logs
- `/opt/weather-bridge/backups` — project backups
- `/opt/weather-bridge/journal` — development handoff/journal

## Isolated server access

- system user: `weather`
- SSH alias: `weather-server`
- rootless Docker socket: `/opt/weather-bridge/runtime/docker/docker.sock`
- Compose project: `weather-bridge`
- deploy lock: `/opt/weather-bridge/runtime/deploy.lock`
- routine operations: `/opt/weather-bridge/bin/deploy`, `restart`, `logs`, `rollback`, `status`

The `weather` user has no write access to other project directories. Production must not depend on a Mac.
