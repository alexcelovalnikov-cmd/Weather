# Security boundaries

Weather is a read-only temperature sensor. Device actions must always return INVALID_ACTION;
OAuth subject, expiry and configured scope must be checked before device access.
Synthetic smoke tests must clear reporting credentials to avoid external notifications.

CI runs hosted with a read-only token, pinned actions and no persisted checkout credentials.
Optional Mac execution requires an independently reviewed exact SHA; do not send untrusted
PR code to self-hosted runners. Server CI and VM execution remain disabled.

Admission and recurring audits follow the Server Admin Controller application contract:
https://github.com/alexcelovalnikov-cmd/Server-Admin-Controller/blob/main/docs/APPLICATION_SECURITY_CONTRACT.md

Review runtime authorization, sensitive data/logging, release integrity, backup/restore and
network boundaries independently. A green isolation audit is not an application certification.
Production release and filesystem changes require a separate reviewed preview/approval.

## Release operation input checks

Source hardening 2026-10-02: ops release selection requires V followed by ASCII
digits, at most 16 characters in total, an existing direct release directory and
no symlink at the releases root or selected release. ensure_image checks this
before Docker; restart validates current-version as deploy/rollback already do.
Synthetic shell tests use temporary directories and a mocked Docker function.

This input check is not a source/CI/image admission gate and does not prevent a
concurrent owner from changing writable directories or replacing operation scripts.
Rootless runtime remains unchanged until a reviewed production preview is applied.
Immutable admission records and filesystem ownership are separate required work.

## Container boundary canary

Prepared source policy: UID/GID 1000, read-only root filesystem, all capabilities
dropped, no-new-privileges and 128-process limit. No production host mounts are
introduced. Hosted CI parses the production Compose policy without reading its
private env file and uses those restrictions in an isolated container with external
network disabled and synthetic OAuth credentials. It verifies effective UID,
capabilities, privilege flag, process limit, denied filesystem writes and OAuth
negative tests. Production still needs a separately reviewed runtime change.

Network-none is a test boundary: production needs weather/Yandex endpoints; no
production egress restriction is claimed. Rootless Docker state is project-owned
and must remain writable. Protecting host operation scripts/releases requires
root-owned immutable paths and a typed admission adapter; recursively changing
all runtime ownership would break the rootless daemon.
