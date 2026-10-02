# Rollback V1

До canary merge/activation: draft PR закрыть по отдельному решению; локальные материалы сохранить.
Исходные workflow не изменялись, production не затронут.

После activation:
1. enabled=false для affected repo; остановить discovery новых задач. Сначала проверить
   active/dispatching/cancelling SQLite intents; не удалять state и не освобождать unknown leases.
2. Новые задачи не создавать; running job дождаться или отменить по exact GitHub run_id.
   Изменение mode само по себе не отменяет running jobs. Подтвердить завершение каждого run.
3. При работающем billing переключить GITHUB; hosted gate только после probe. Если billing blocked,
   rollback не может обещать успешный hosted CI — оставить failed/blocked status и локальный manual check.
4. Restore original native workflow из audited base commit/reviewed rollback PR, а не из mutable
   текущего main. Снять hybrid/ci requirement только вместе с возвращением обязательного старого CI.
5. Дерегистрировать только известные runner IDs; остановить listener, уничтожить disposable guests.
   Не удалять Docker images/containers/volumes production и не менять SAC live installation.
6. Остановить coordinator service после reconciliation; отозвать dedicated runtime/issuer credentials;
   state/logs хранить для диагностики. Никаких PAT в GitHub commit/чат.

При аварии GitHub API status/cancel невозможно гарантировать. Не делать новую попытку до read-back.
GitHub native self-hosted queue всё равно имеет platform timeout24h; наш120s bound действует,
когда coordinator и API доступны. External watchdog для dispatcher heartbeat обязателен при activation.
