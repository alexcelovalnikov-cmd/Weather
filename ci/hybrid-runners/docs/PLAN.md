# План V1 — 02.10.2026

1. Read-only аудит четырёх репозиториев, Actions API и SAC live: выполнен; сырые workflow в audit/.
2. Независимый Python диспетчер GitHub API: AUTO / LOCAL / GITHUB, совместимость Linux/Docker,
   состояние SQLite, журнал JSON, health TTL, ограничение очереди, отдельные dispatch attempts,
   aggregate commit status hybrid/ci. Никаких deploy, тестовые ошибки не перезапускаются.
3. Аддитивные hybrid-ci.yml для Weather → SAC → Telegram Manager → RentRabbit.
   Определение workflow закрепляется immutable tag; исходники checkout по точному SHA.
   Существующие CI не отключаются до E2E. Импорт и stage mutation не маршрутизируются.
4. Офлайн unit/integration/fault tests, проверка workflow и локальный Weather smoke.
5. Checkpoint GitHub: workflow-write access; add canary workflow на main и immutable tag;
   runtime Actions write + statuses write + Contents read + Pull requests read.
6. Checkpoint Mac: отдельная VM/account, ephemeral runner только Weather; token отдельно,
   без GitHub PAT внутри job. Checkpoint Linux: изолированная CI VM/host + rootless Docker;
   production Docker socket не передавать. Текущий сервер не считать готовым Docker runner.
7. E2E canary: Mac online/offline; Linux online/offline; hosted allowed/blocked;
   исчезновение runner после выбора; queue deadline; failure без retry; рестарт диспетчера.
8. Только после gate #7 — последовательное включение остальных проектов и cutover triggers.
   Контроль состояния hybrid/ci и branch-protection capability. Rollback сохраняет исходный CI.

Checkpoint регистрации/установки требует действий пользователя и отдельного preview/apply SAC.
Локальная реализация и тесты разрешены текущим поручением. До gate #7 rollout не выполняется.
