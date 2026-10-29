#!/usr/bin/env python3
"""Reject credential-shaped strings in tracked source, without echoing matches."""
import pathlib
import re
import subprocess
import sys
root=pathlib.Path(sys.argv[1])
patterns=[re.compile(r'\b\d{5,16}:[A-Za-z0-9_-]{30,}\b'),re.compile(r'\bsk-[A-Za-z0-9_-]{24,}\b'),re.compile(r'-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----')]
paths=subprocess.check_output(['git','-C',str(root),'ls-files','-z']).decode().split('\0')
fail=[]
for name in filter(None,paths):
    data=(root/name).read_bytes().decode('utf-8',errors='ignore')
    if any(p.search(data) for p in patterns):fail.append(name)
if fail:
    print('SECRET SCAN FAILED: '+', '.join(fail));sys.exit(1)
print('Secret scan passed')
