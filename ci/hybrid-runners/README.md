# GitHub Hybrid Runners V1

Подготовлены реализация, read-only аудит и [draft canary PR3](https://github.com/alexcelovalnikov-cmd/Weather/pull/3).
Общий пакет находится в Weather `ci/hybrid-runners/`, templates остальных repo не активированы.
Система **не активирована**:
все repositories.enabled=false, hosted fallback выключен, runners=0.
Canary — Weather; следующие этапы требуют инфраструктурных checkpoints и live E2E.

## Что реализовано

Независимый coordinator (Python3.9+, SQLite, без внешних Python зависимостей) наблюдает
main/stage и merge SHA открытых PR. Выбирает проверенный runner ДО workflow dispatch.
В GitHub запускается отдельная попытка hybrid-ci.yml с явным runner и immutable source SHA.
Workflow definition берётся из tag hybrid-runtime-v1, привязанного к reviewed SHA в config.
Tag drift блокирует dispatch. GitHub остаётся местом хранения кода, PR, статусов и логов.
Coordinator не выполняет тестовый код и не получает production/deploy доступ.

AUTO: Linux → hosted для Linux/Docker; для Weather Mac → Linux → hosted.
LOCAL: только совместимые local runners; при отсутствии ёмкости status error без GitHub queue.
GITHUB: только hosted, причём оператор должен подтвердить availability успешным probe.
Изменение config применяется к новым попыткам без переписывания workflow.
Fork/неразрешённый автор PR направляется только hosted. При billing block такой PR блокируется,
а не исполняется на личном Mac/production сервере.

Очередь незапущенной попытки ограничена 120 секундами + polling/API latency.
Coordinator отменяет run, ждёт confirmed cancelled и заново проверяет jobs перед fallback.
Назначенный runner, выполняемый step, test failure, cancelled пользователем, skip/пустой success
не разрешают повтор. Billing annotation с runner_id=0 и пустыми steps разрешает fallback.
Потерянный HTTP ответ на dispatch сохраняется как unresolved intent; дублирование запрещено.
Для неопределённого dispatch outcome lease сохраняется до ручной сверки.

## Проверка

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q hybrid scripts tests
```

Четыре аддитивных workflow в overlays/. Actions закреплены commit SHA.
Их проверяет actionlint; exact pins сохранены в audit/action-pins.json.
Изначальные CI не менялись. RentRabbit обе версии Python выполняются последовательно в одном job,
чтобы один ephemeral runner выполнил полный suite. Import/stage mutation excluded.

## Запуск после checkpoints

1. Добавить canary workflow в default main без отключения старого CI; зафиксировать reviewed
   commit в неизменяемом tag hybrid-runtime-v1. В config вписать exact SHA.
2. Provision worker VM, регистрацию и health — см. docs/CHECKPOINTS.md.
3. Скопировать config.example.json в operator-owned config.json, enabled=true только Weather.
   Установить routes [local-mac, local-linux, github-linux], проверенные runner names.
4. На отдельном coordinator account/host: runtime credential только selected repositories,
   Contents read, Pull requests read, Actions write, Commit statuses write; runner-list permission
   Administration read. Registration credential Administration write держать отдельно.
5. Запустить из корня пакета с локальными state/health:

```sh
python3 -m hybrid.broker --config config.json --state state/broker.sqlite --health health
```

В Linux service пути в docs/hybrid-coordinator.service соответствуют отдельному CI project,
а не SAC install dir. systemd credential хранится вне workers. Service не устанавливался.
VM manager должен атомарно доставлять health JSON в coordinator-owned health directory;
workflow account не имеет туда write access. Публикация по существующему authenticated SSH
или VM-manager channel настраивается в infrastructure checkpoint, не через публичный HTTP.

Первый polling baseline не запускает все исторические heads/PR. Текущий canary запускается явно:

```sh
python3 -m hybrid.broker --config config.json --state state/broker.sqlite --health health \
  --enqueue alexcelovalnikov-cmd/Weather EXACT_40_HEX_SHA canary --once
```

Команда вручную допускает local только для текущего SHA разрешённой ветки.
Новые PR после baseline и изменённые heads наблюдаются автоматически.
Polling проверяет последний observed head; промежуточные быстрые pushes могут быть coalesced.
Для гарантированной обработки каждого push нужен durable webhook inbox, в V1 его нет.

## Наблюдаемость и переключение

```sh
python3 scripts/control.py --config config.json --state state/broker.sqlite
python3 scripts/control.py --config config.json --mode LOCAL
python3 scripts/control.py --config config.json --mode AUTO
```

Commit status hybrid/ci на SOURCE SHA — канонический результат всего CI, включая fallback.
GitHub native status Hybrid CI относится к runtime-tag SHA; для PR нельзя требовать его вместо
hybrid/ci. До cutover старые CI продолжают работать отдельно, возможны параллельные результаты.
Обязательный hybrid/ci в private Weather сейчас нельзя enforced через branch protection на
текущем тарифе (API403): отдельный checkpoint плана/правил, не имитировать enforcement.

SQLite хранит задачи, попытанные routes, активный nonce/run_id, host lease и heartbeat.
JSON journal events связывают task → route → nonce → GitHub run. Логи systemd удерживать
оператором минимум7 дней; регистрационные _diag логи собирать в закрытое VM-management storage.
Операторский контроль: heartbeat старше60 сек, dispatch outcome unknown, expired health,
billing_blocked, runtime tag drift, no capacity, повторные API ошибки — требуют внимания.
Автоматические уведомления/монитор не создавались; внешний service watchdog требуется при установке.

Включать hosted только после успешного одноразового hosted canary/probe:

```sh
python3 scripts/control.py --config config.json --state state/broker.sqlite \
  --hosted-verified-minutes 30 --mode AUTO
```

TTL max60 минут. Billing failure latch запрещает hosted для всех repo до нового успешного probe
и явного сброса через control.py. Нет достоверного API boolean «оплата доступна».
После первоначального checkpoint можно включить `--hosted-auto-probe`: диспетчер запускает
безвредную пробу только при необходимости hosted fallback, без checkout и secrets.
Успех даёт TTL15min и сбрасывает billing latch; отказ даёт cooldown15min.
В LOCAL и при `--hosted-block` новые пробы запрещены. Probe default disabled.
Потерянный ответ probe сохраняется как unknown и требует сверки без повторного POST.

## Границы

Диспетчер должен работать на постоянном узле отдельно от Mac. systemd restart + durable SQLite
дают restart recovery на одном узле; одновременный запуск двух координаторов запрещён file lock.
Если и coordinator, и все local узлы недоступны, при заблокированном hosted billing полностью
автоматический CI невозможен. Нужен независимый always-on coordinator/VM. Установка на текущем
production сервере только по отдельному SAC preview/apply, без root shell.
Смена GITHUB/LOCAL не меняет уже начавшийся job. Только новые задачи/попытки получают новый mode.
Терминальные blocked/error задачи не переигрываются автоматически после появления ёмкости:
проверенный операторский retry должен сверить source SHA и отсутствие активных runs.
Повторяемая registration реализована; VM provisioning/restore и fleet rearm пока обязательны
внешнему VM manager. Ephemeral registration сама по себе не очищает VM. Перед промышленной
активацией нужен проверенный restore/rearm цикл; scripts не предоставляют неподтверждённую VM фабрику.

Rollback, E2E gates и ограничения текущего сервера: docs/CHECKPOINTS.md, docs/E2E.md,
docs/ROLLBACK.md, docs/AUDIT.md и docs/PLAN.md.
