"""Bounded GitHub REST adapter. Credentials stay in coordinator process only."""
import json
import os
import subprocess
import urllib.request
import urllib.error
import urllib.parse

class APIError(RuntimeError):
    pass

class GitHub:
    def __init__(self):
        self.token = os.environ.get('GH_TOKEN')
        if not self.token:
            self.token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()

    def request(self, method, path, data=None):
        if not path.startswith('/') or '://' in path:
            raise ValueError('GitHub API paths only')
        req = urllib.request.Request('https://api.github.com'+path,
            data=json.dumps(data).encode() if data is not None else None, method=method,
            headers={'Authorization':'Bearer '+self.token, 'Accept':'application/vnd.github+json',
                     'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'hybrid-runners-v1'})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                raw=response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            # Never print raw authenticated response or headers.
            raise APIError(f'{method} {path.split("?")[0]} HTTP {e.code}') from None
        except (TimeoutError, OSError) as e:
            raise APIError(f'{method} {path.split("?")[0]} transport failure') from None

    def pages(self, path, key=None):
        result=[]
        for page in range(1, 21):
            sep='&' if '?' in path else '?'
            data=self.request('GET',path+f'{sep}per_page=100&page={page}')
            items=data[key] if key else data
            result.extend(items)
            if len(items)<100:return result
        raise APIError('pagination bound exceeded')

    def get(self, path):return self.request('GET',path)
    def post(self, path, data=None):return self.request('POST',path,data)

    def ref_sha(self, repo, ref):
        obj=self.get(f'/repos/{repo}/git/ref/tags/'+urllib.parse.quote(ref,safe=''))['object']
        for _ in range(4):
            if obj['type']=='commit': return obj['sha']
            if obj['type']!='tag': break
            obj=self.get(f'/repos/{repo}/git/tags/'+obj['sha'])['object']
        raise APIError('runtime ref must resolve to commit')
