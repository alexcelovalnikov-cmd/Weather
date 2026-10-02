"""Fail-closed routing. No GitHub-hosted bootstrap job and no workflow code here."""
from dataclasses import dataclass
import time

LABELS = {
    'local-mac': ['self-hosted', 'macOS', 'ARM64', 'local-mac', 'hybrid-v1'],
    'local-linux': ['self-hosted', 'Linux', 'X64', 'local-linux', 'hybrid-v1'],
    'github-linux': ['ubuntu-latest'],
}

@dataclass(frozen=True)
class Candidate:
    route: str
    host_id: str
    runner_id: int = 0


def choose(config, policy, runners, health, attempted=(), trusted=True, leased=(), now=None):
    now = time.time() if now is None else now
    mode = config['mode']
    if mode not in ('AUTO', 'LOCAL', 'GITHUB'):
        raise ValueError('invalid mode')
    preference = policy['routes'] if mode != 'GITHUB' else ['github-linux']
    for route in preference:
        if route in attempted or route not in policy['routes']:
            continue
        if route == 'github-linux':
            if mode == 'LOCAL':
                continue
            gate = config.get('hosted', {})
            # Operator enables only after a successful hosted probe; unknown is denied.
            if not gate.get('denied') and gate.get('allowed') is True and now < gate.get('verified_until', 0):
                return Candidate(route, 'github-hosted')
            continue
        if mode == 'GITHUB' or not trusted:
            continue
        for runner in runners:
            allowed = policy.get('runner_names', {}).get(route, [])
            if runner['name'] not in allowed or runner.get('status') != 'online' or runner.get('busy'):
                continue
            labels = {x['name'].lower() for x in runner.get('labels', [])}
            if not ({x.lower() for x in LABELS[route]} | {runner['name'].lower()}) <= labels:
                continue
            h = health.get(runner['name'], {})
            age = now - h.get('observed_at', 0)
            if not h.get('healthy') or age < 0 or age > config.get('health_ttl', 90):
                continue
            if not set(policy['capabilities']) <= set(h.get('capabilities', [])):
                continue
            host = h.get('host_id')
            if not host or host in leased:
                continue
            return Candidate(route, host, runner['id'])
    return None
