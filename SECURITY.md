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
