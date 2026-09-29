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
- `/opt/weather-bridge/data` — persistent app/runtime data
- `/opt/weather-bridge/logs` — project logs
- `/opt/weather-bridge/backups` — project backups
- `/opt/weather-bridge/journal` — development handoff/journal

## Isolated server access

- system user: `weather`
- SSH alias: `weather-server`
- project path: `/opt/weather-bridge`
- rootless Docker socket: `/run/user/<weather uid>/docker.sock`
- Compose project: `weather-bridge`
- deploy lock: `/opt/weather-bridge/runtime/deploy.lock`
- routine operations: `/opt/weather-bridge/bin/deploy`, `restart`, `logs`, `rollback`, `status`
- GitHub: `alexcelovalnikov-cmd/Weather`

The `weather` user has no write access to the other project directories. Root is emergency/host-level access only. Production does not depend on a Mac.
