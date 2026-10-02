# Infrastructure checkpoints V1

## C1 — GitHub canary

Review additive Weather PR: manual hybrid-ci.yml + общая coordinator реализация.
Merge только canary manual workflow в main; исходный ci.yml и production не менять.
Зафиксировать reviewed commit tag hybrid-runtime-v1 (не перемещать tag), exact SHA в config.
Runtime credential для четырёх selected private repos:
Contents read, Pull requests read, Actions write, Commit statuses write,
Administration read для runners list. Registration token issuer: отдельная Administration write.
CLI token сейчас не имеет workflow scope; upload через имеющийся GitHub connector проверяется
отдельно и не требует передачи PAT в чат. Секреты предоставлять только локальному secure storage.

## C2 — Mac canary registration

Подтвердить запуск в отдельной disposable macOS ARM64 VM на Mac; не в личном aleks account.
Guest: runner user без admin/sudo, без shared home, SSH keys, Obsidian, production credentials,
host directories и native connector tokens. Image с Node24 + bash + Git + исходящей HTTPS.
Рабочая ёмкость один job, max25min. Runner label/name hybrid-weather-mac.

Оператор скачивает актуальный официальный actions/runner archive с GitHub registration page,
проверяет предоставленный SHA256 и запускает script **в guest**. Token с TTL1h выдаётся
контролируемым issuer вне worker guest; в guest поступает только одноразовый registration token.
Пример после checkpoint (не запускался):

```sh
# Registration token is piped on stdin, not copied to chat or command arguments.
python3 scripts/register-runner.py \
 --repo alexcelovalnikov-cmd/Weather --route local-mac --name hybrid-weather-mac \
 --archive /approved/actions-runner-osx-arm64.tar.gz --sha256 REVIEWED_SHA256 \
 --workdir /isolated/runner --approved-disposable-vm
```

Команда читает token на stdin. В environment не передавать registration PAT.
`./run.sh` запускается в зарегистрированном worker dir с отключёнными GH_TOKEN/GITHUB_TOKEN.
VM manager получает PID Runner.Listener и обновляет health примерно каждые15 сек через health.py;
JSON передаётся coordinator-owned channel. Для Mac нужны capabilities node24; health TTL90сек.
После одного job runner автоматически deregistered; manager сохраняет защищённые diagnostics,
уничтожает guest или restores approved snapshot, затем регистрирует свежий runner.
До проверки restore/rearm не включать automatic production workload.

## C3 — Linux + постоянный coordinator

Текущий production сервер не считать безопасной CI VM: 2 cores/4GB, ~1.44GB safe RAM headroom.
Heavy Telegram/RentRabbit Docker build needs measured resources on отдельной CI VM/host;
рекомендуемый стартовый budget для проверки: 2 cores/4GB и20GB disk отдельно от production.
Это начальная оценка, E2E измеряет peak и окончательный budget. Покупка сервера не выполнялась.

Worker: Linux X64, dedicated unprivileged user, rootless Docker + Compose и отдельные filesystem/network.
Нельзя подключать /var/run/docker.sock production, /opt проектов, SSH/deploy keys, SAC maintenance adapters.
Docker builds/network tests используют только VM daemon. Cgroup/resource limits VM не зависят от workflow.
Один physical capacity host_id и один leased CI job одновременно на весь общий host;
один repo-level ephemeral runner registration на соответствующую repo.
Labels self-hosted/Linux/X64/local-linux/hybrid-v1 + reviewed runner_name.
Python3.12/Node22 для SAC/TM, Python3.9/3.12+rootless Docker для RR, Node24 для Weather.
Фабрика VM должна иметь approved templates для capabilities и verified restore/rearm lifecycle.

Coordinator: отдельный ci-coordinator user/project, 256MB max, CPUQuota10%, no job code,
systemd unit в docs/, token через LoadCredential, state SQLite и readonly config/code.
Health dir доступен VM manager на запись; runner account не имеет доступа.
Перед серверными write подготовить immutable SAC create-project/filesystem preview,
получить explicit approval и применить через typed controller. SAC сам не регистрировать как /opt проект.
Текущий SAC contract не предоставляет runner-install capability: не обходить это root shell.
Runbook/VM service остаются infrastructure checkpoint, а не «обычным deploy проекта».

## C4 — hosted availability

Запустить отдельный безвредный hosted probe manual Workflow (Weather): проверяем owner billing.
После фактического success можно включить короткий TTL hosted gate.
Blocked billing → не включать fallback. UNKNOWN → deny. Пробу не запускали.
Hosted gate автоматом выключается по TTL/failed-payments annotation. После первоначального
checkpoint можно включить `--hosted-auto-probe`: без checkout, permissions:{}, timeout1min.
Проба только по необходимости fallback; TTL и cooldown15min. Успех восстанавливает gate.
Расход ограничен одной пробой на15min при активной потребности; billing определяется тарифом.
В LOCAL и при `--hosted-block` новые пробы запрещены. Unknown outcome блокирует дальнейшие
пробы до manual reconciliation. Никакой probe run пока не выполнялся.

## Gate перед rollout

Сценарии docs/E2E.md должны иметь GitHub run URL, SOURCE SHA, dispatcher trace,
vm lifecycle proof и peak resources. Только после success последовательно SAC → TM → RR.
Выдача широкого доступа к production Docker не является способом пройти этот gate.
