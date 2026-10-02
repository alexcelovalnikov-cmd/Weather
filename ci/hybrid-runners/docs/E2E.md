# Canary E2E gate

Статус: NOT RUN. Рunners отсутствуют; offline tests и local Weather smoke не являются GitHub E2E.
В config enabled=false у всех четырёх repo. Ни один project cutover не выполнен.

| Scenario | Expected outcome | Live evidence |
|---|---|---|
| Weather Mac healthy, AUTO | Mac ARM64, OAuth smoke pass, hybrid/ci success на SOURCE SHA | pending |
| Mac offline + Linux healthy | Linux, Mac job вообще не dispatch | pending |
| Mac/Linux offline + hosted verified | ubuntu-latest, target SHA тот же | pending |
| All locals offline + billing blocked/UNKNOWN | error status, no queued jobs | pending |
| Runner disappears after health check | queue timeout120s → cancel confirmed → next route | pending |
| Cancel races start | fail/no retry/no second run | pending |
| LOCAL + no local capacity | error, no hosted spending | pending |
| GITHUB + billing failed annotation | fail/block, no local job under GITHUB | pending |
| Test fails after job start | failure, no fallback/no hidden green | pending |
| Restart after accepted dispatch | find exact nonce, no duplicate | pending |
| Lost dispatch response | reconcile nonce; unresolved error, no blind second POST | pending |
| VM one-shot/reset/rearm, second commit | fresh runner accepts job, no state/secret contamination | pending |
| Untrusted/fork PR | hosted only or blocked; never Mac/Linux | pending |
| Source changes workflow | pinned runtime tag still supplies job definition | pending |
| Runtime tag moves | dispatch denied | pending |
| Mode changes | new attempts use new mode, started job unchanged | pending |

После Weather пройти Linux SAC suite и проверить /tmp/port isolation; затем Telegram Docker build
без production socket и измерить RAM/disk/CPU; затем RR sequential3.9+3.12 + isolated container tests.
Ни import-source.yml, ни orphan apply-v2-stage workflow не запускать.
Cutover review: status hybrid/ci на PR merge/head, branch rules capability, coordinator heartbeat watchdog,
API outage recovery, VM lifecycle, resource peaks, manual rollback на hosted с рабочим billing.
