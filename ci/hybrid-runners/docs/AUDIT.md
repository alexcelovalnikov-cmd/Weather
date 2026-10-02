# Read-only аудит — 02.10.2026

Все четыре репозитория private, main; owner — личный User alexcelovalnikov-cmd,
repo runners = 0. Runner groups доступны организациям: здесь repo-level registrations,
по одному runner identity на репозиторий, общая локальная ёмкость сериализуется диспетчером.
GitHub CLI авторизован repo/read:org/gist, без workflow scope; секреты не выгружались.
Weather branch protection API возвращает 403 upgrade required; обязательный hybrid/ci
не считать enforced до изменения тарифа/проверки правил.

| Репозиторий | Workflow | Совместимость / эффект |
|---|---|---|
| telegram-manager | ci.yml, push main/stage, PR main/stage | Linux + Compose + Docker build + Python3.12 + Node22; timeout15 |
| telegram-manager | import-source.yml | bootstrap push, contents:write, commit/push main/stage; исключён |
| Server-Admin-Controller | ci.yml, push/PR main | Python3.12 + Node22, Linux filesystem/client smoke; Linux only до отдельной Mac квалификации |
| rentrabbit-chatgpt-connector | tests.yml, push/PR | Python3.9/3.12 matrix + Docker build/run --network none; Linux only |
| rentrabbit-chatgpt-connector | apply-v2-stage.yml (API listing) | отсутствует в main tree и stage ref404; исторический source прочитан по последнему run SHA, mutation workflow исключён |
| Weather | ci.yml, push main/stage, PR main | Node24 syntax + OAuth offline smoke; Mac ARM64 кандидат canary |

Последние TM, SAC, RR annotations: job was not started because recent account payments
have failed or spending limit needs to be increased. Это billing evidence, не ошибка тестов.
Weather предыдущие runs успешны; новый CI draft PR3 тоже заблокирован оплатой до начала шагов:
https://github.com/alexcelovalnikov-cmd/Weather/actions/runs/36984852043
Текущая hosted доступность BLOCKED; fallback/probe выключены по умолчанию.
GitHub billing API не считается достоверным boolean: доступ к runner подтверждает probe,
затем разрешение fallback имеет ограниченный TTL и сбрасывается billing annotation.

SAC live V27, HEALTHY; nginx syntax OK; service active. Root broker только typed capabilities,
normal root shell запрещён. Runtime не зависит от plugin. 2 CPU, 4.1 GB RAM,
recent-peak safe RAM headroom ~1.44 GB, safe CPU headroom1.3 cores, disk headroom27.7GB.
Production TM 6 running containers ~598MB, RR1 ~64MB. Старые остановленные releases не удалялись.
Isolated TM/RR filesystem policy managed; Weather staging-only management, runtime0 containers.
Для CI нужна отдельная VM с лимитами, собственным rootless Docker daemon и без /opt production.
Прямой доступ к production Docker равнозначен root и в проект не включается.

Mac ARM64, macOS27.0.1; Node24.21.0 доступен; Docker не установлен. Runner не зарегистрирован.
UTM/Parallels/VMware/VirtualBuddy/OrbStack/Docker.app и tart/limactl/multipass не обнаружены.
Actionlint1.7.12 скачан в локальную tools/ с проверкой официального checksum для validation.
SAC не имеет typed runner-install capability. Установка runner не маскируется под deploy:
подготовлен runbook с отдельным infrastructure checkpoint, root console не использовалась.

Источники: audit/<repo>.json и audit/<repo>/.github/workflows; SAC get_server_health,
get_capacity, list_projects, get_control_plane_status, get_client_contract.
GitHub docs: https://docs.github.com/en/actions/reference/runners/self-hosted-runners
https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access
https://docs.github.com/en/actions/reference/security/secure-use

Исторический apply-v2-stage восстановлен read-only по run36544355130, stage,
SHA8fafcf0ae8f9627d3de3b7d671c019bfaa10cfd0. Push stage при изменении .stage/V2.patch.xz:
применяет patch, удаляет patch/свой workflow, запускает Python3.9/3.12 и Docker acceptance,
затем commit/push HEAD:stage с contents:write. Это изменение исходников, не production deploy;
в routing allowlist не включён. Snapshot audit/rentrabbit-chatgpt-connector/orphan-apply-v2-stage.yml.
