import argparse, hashlib, json, re, urllib.request
from pathlib import Path
parser=argparse.ArgumentParser(description='Hash-lock exact versions exported by pip freeze from a validated Python 3.12 environment.')
parser.add_argument('resolved', type=Path)
parser.add_argument('target', type=Path)
parser.add_argument('--direct', required=True, type=Path)
args=parser.parse_args()
freeze=args.resolved.read_text().splitlines()
target=args.target
lines=['# Direct requirements sha256: '+hashlib.sha256(args.direct.read_bytes()).hexdigest(), '# CPython 3.12 / Linux amd64. Exact deployed versions plus verified PyPI archive hashes.', '# Regenerate using scripts/lock_python.py; do not edit individual hashes.', '']
for requirement in freeze:
 if not requirement.strip() or requirement.startswith('#'): continue
 if not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+', requirement): raise ValueError('Expected exact name==version: '+requirement)
 name,version=requirement.split('==')
 with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as r: meta=json.load(r)
 hashes=sorted({f['digests']['sha256'] for f in meta['urls'] if not f.get('yanked')})
 if not hashes: raise RuntimeError('No non-yanked archives for '+requirement)
 lines.append(requirement+' \\')
 lines.extend('    --hash=sha256:'+h+(' \\' if i<len(hashes)-1 else '') for i,h in enumerate(hashes))
 lines.append('')
target.write_text('\n'.join(lines))
print('Locked',len(freeze),'requirements into',target.name)
