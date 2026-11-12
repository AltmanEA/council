#!/usr/bin/env python3
"""Manifest/disk version parity check (compliance rule 6 of mvp-interfaces audit rules)."""
import re, os, sys

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
m = open('docs-manifest.yaml').read()
blocks = re.split(r'\n  - id: ', '\n' + m)
bad = 0
for b in blocks[1:]:
    did = b.split('\n')[0].strip()
    path = re.search(r'path: (\S+)', b)
    ver = re.search(r'version: (\S+)', b)
    if not path or not ver:
        continue
    p, v = path.group(1), ver.group(1)
    if not os.path.exists(p):
        print(f"MISSING FILE: {did} -> {p}")
        bad += 1
        continue
    head = open(p).read(400)
    mv = re.search(r'^Version: (\S+)', head, re.M)
    mv = mv.group(1) if mv else '?'
    flag = "OK " if mv == v else "MISMATCH"
    if mv != v:
        bad += 1
    print(f"{flag} {did}: manifest={v} disk={mv}")
print('---')
print('FAIL' if bad else 'ALL PARITY OK', f'({bad} issues)')
sys.exit(1 if bad else 0)
