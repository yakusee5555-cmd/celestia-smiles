#!/usr/bin/env python3
"""Deploy ~/workspace/celestia-smiles to Vercel as a static site.

SHA file-upload flow (same as crawio-system-diagram): upload each file to
/v2/files by SHA-1 digest, then create the deployment referencing
{file, sha, size}. NEVER base64 file contents into the deployment payload.
Auth via the same surrogate helper vc.py uses; this script never sees the token.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request, DynamicCredentialError

BASE = "https://api.vercel.com"
CREDENTIAL = "custom.vercel"
ALLOWED_HOSTS = ["api.vercel.com"]
PROJECT = "celestia-smiles"
FILES = [
    "index.html",
    "assets/testimonials/aesthetic-before.jpg",
    "assets/testimonials/aesthetic-after.jpg",
    "assets/testimonials/ortho-before.jpg",
    "assets/testimonials/ortho-after.jpg",
    "assets/testimonials/implant-before.jpg",
    "assets/testimonials/implant-after.jpg",
    "assets/testimonials/whitening-before.jpg",
    "assets/testimonials/whitening-after.jpg",
]


def call(method, path, body=None, extra_headers=None):
    req = urllib.request.Request(BASE + path, data=body, method=method.upper(),
                                 headers={"User-Agent": "jarvis-agent"})
    for k, v in (extra_headers or {}).items():
        req.add_header(k, v)
    add_surrogate_to_request(req, CREDENTIAL, entry_name="access_token", allowed_hosts=ALLOWED_HOSTS)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                return resp.status, {"raw": raw.decode("utf-8", errors="replace")[:500]}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise DynamicCredentialError(f"Vercel {method} {path} -> HTTP {exc.code}: {detail}")


def main():
    os.chdir("/home/hatch/workspace/celestia-smiles")
    entries = []
    for name in FILES:
        data = open(name, "rb").read()
        sha = hashlib.sha1(data).hexdigest()
        status, _ = call("POST", "/v2/files", body=data,
                         extra_headers={"Content-Type": "application/octet-stream",
                                        "x-vercel-digest": sha})
        print(f"uploaded {name} ({len(data)} bytes, sha1 {sha}) -> {status}", flush=True)
        entries.append({"file": name, "sha": sha, "size": len(data)})

    status, dep = call("POST", "/v13/deployments", body=json.dumps({
        "name": PROJECT,
        "target": "production",
        "files": entries,
        "projectSettings": {"framework": None},
    }).encode("utf-8"), extra_headers={"Content-Type": "application/json"})
    print(f"deployment -> {status}: id={dep.get('id')} url={dep.get('url')} state={dep.get('readyState')}", flush=True)
    dep_id = dep["id"]
    state = None
    for _ in range(40):
        _, cur = call("GET", f"/v13/deployments/{dep_id}")
        state = cur.get("readyState")
        print(f"  state: {state}", flush=True)
        if state in ("READY", "ERROR", "CANCELED"):
            break
        time.sleep(5)
    alias = f"https://{PROJECT}.vercel.app"
    print(f"alias: {alias} (final state: {state})")
    return 0 if state == "READY" else 1


if __name__ == "__main__":
    sys.exit(main())
