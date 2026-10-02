# Direct Mac — user decision 2026-10-02

User explicitly requested running directly on the current Mac, without a macOS VM.
The image download was stopped; Tart cleared its partial temporary data (vm-runtime8KB).
Existing VM instructions apply only to future disposable Linux workers, not this Mac.

Weather only: native macOS ARM64, Node24, runner label hybrid-weather-mac.
Registration requires --approved-direct-mac, still --ephemeral (one job per registration),
unprivileged current user, verified official runner archive, fresh project-owned work directory.
No service/sudo/system installation is needed for a canary. No production deploy runs.

Direct execution uses the current macOS account. A fresh runner work directory and sanitized
environment do not isolate its filesystem, Keychain or network permissions. This must never
be described as disposable VM isolation or a host reset. Only reviewed Weather source is
eligible: set repositories[Weather].direct_mac_approved_shas to the exact reviewed commit SHAs.
The broker removes local-mac for other source SHAs, leaving compatible Linux/verified hosted
routes according to mode. Fork/untrusted PRs remain ineligible for any local route.

After each job: verify GitHub run/jobs result and ephemeral deregistration; stop the listener;
preserve diagnostic logs with mode0700 and remove only the known project-owned runner workspace.
Rearming requires a fresh extraction and registration; no host-wide wipe or VM reset claim.
Do not install unrestricted automatic rearm/discovery on this account.

Rollback: disable Weather dispatch in config, reconcile active intents, stop exact listener,
delete the known repository runner ID if still registered. Native CI and production remain intact.
Linux/Docker jobs in the other repos retain local-linux/github-linux routes.
