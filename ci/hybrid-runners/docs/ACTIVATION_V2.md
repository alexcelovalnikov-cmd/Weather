# Activation V2 — 2026-10-02

User authorized continuing the Mac registration checkpoint and explicitly approved SAC preview
`e9e85cd1eaa76b97df154f77`, digest `e763307e2d6fac3399fe6a72eb7369da984dc371e40d9ab719d998a75870d3ea`.
SAC applied project_new at08:58:25UTC: ci-coordinator user uid/gid1005, /opt/ci-coordinator,
separate SSH identity/alias. SSH id verified; existing TM/RR project directories not writable.
Typed SAC audit: Isolation/Account/Filesystem/Adapters OK. No service or CI was started by this preview.

Staged code only in /opt/ci-coordinator/staging/code-review; 40 offline tests passed there.
Local tests now41 include token environment validation against the current runner input interface.
SAC expected resource budget is advisory; actual service cgroup limits still require installation.
User service Linger=no; no daemon setup was attempted. Production runtime remains unchanged.

Mac: Tart2.40.1 installed project-locally in tools/tart/tart.app; official release checksum verified
and codesign --verify --deep --strict succeeded. TART_HOME=project/vm-runtime;
TART_NO_AUTO_PRUNE=1. No Homebrew/system install. Base macOS Tahoe image download in progress.
VM has not yet booted; runner has not yet registered. No host shared folders/clipboard planned.

Runner archive v2.337.0 macOS ARM64, SHA256
5a2cd92908a93d7276a194e1de6008099f3e7946f3f8e14aa7a1a7b4a31fdec2 verified.
Archive contains six normal internal symlinks for Node/npm/corepack. Helper now extracts regular
members first and validates/creates internal relative symlinks last; traversal/absolute/device/
hardlink and file-below-symlink cases denied. Extraction of actual verified release succeeded.
Current runner source uses ACTIONS_RUNNER_INPUT_TOKEN; helper corrected and fixture-tested to
keep one-time token out of argv/logs and remove ambient GH_TOKEN/GITHUB_TOKEN.

Linux heavy worker request (1CPU, 2048MB, 20GB) fails safe capacity check:
recent RAM headroom1.44GB. No Docker daemon/socket or Linux worker installed on production server.

Remaining: complete base download/boot, create non-admin VM worker, verify isolation,
prepare/reset template, canary default workflow immutable tag, ephemeral registration,
live CI and reset/rearm proof; coordinator restricted credential and typed service-install checkpoint.
