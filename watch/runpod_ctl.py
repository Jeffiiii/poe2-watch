"""Minimal RunPod control from the command line (REST API v1, key from poe2-watch/.env as RUNPOD_API_KEY; never printed).

  python watch/runpod_ctl.py list
  python watch/runpod_ctl.py terminate <podId>
  python watch/runpod_ctl.py stop <podId>
  python watch/runpod_ctl.py create <name> <run.sh presigned url> [--gpu "NVIDIA GeForce RTX 5090" ...] [--image runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404]
      -> a pod whose start command fetches run.sh and runs it in the background, then the template's /start.sh (Jupyter stays available);
         ports 8888/http, 8000/http (results server), 22/tcp; prints the pod id and the results URL
"""
import json
import os
import sys
import urllib.request

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
load_dotenv("C:/Users/Leo12/Documents/Living-Character-Platform/.env")      # the owner keeps RUNPOD_API_KEY there (2026-10-06); only this variable is read
KEY = os.environ.get("RUNPOD_API_KEY")
if not KEY:
    sys.exit("RUNPOD_API_KEY is not set in poe2-watch/.env")
BASE = "https://rest.runpod.io/v1"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json", "User-Agent": "poe2-watch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
if cmd == "list":
    st, pods = call("GET", "/pods")
    if st != 200:
        sys.exit(f"HTTP {st}: {pods}")
    for p in pods or []:
        print(p.get("id"), p.get("name"), p.get("desiredStatus"), p.get("machine", {}).get("gpuTypeId") if isinstance(p.get("machine"), dict) else p.get("gpuTypeId"), p.get("costPerHr"))
    if not pods:
        print("no pods")
elif cmd == "create":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("name")
    ap.add_argument("url")
    ap.add_argument("--gpu", action="append", default=[])
    ap.add_argument("--image", default="runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404")
    ap.add_argument("--disk", type=int, default=30)
    ap.add_argument("--cloud", default="SECURE")
    ap.add_argument("--ports", default="8888/http,8000/http,22/tcp")
    ap.add_argument("--entrypoint", action="store_true", help="also override the image ENTRYPOINT (images whose entrypoint is a server, e.g. vllm/vllm-openai)")
    ap.add_argument("--raw", action="store_true", help="run the fetched script directly, without the template's /start.sh")
    a = ap.parse_args()
    gpus = a.gpu or ["NVIDIA GeForce RTX 5090"]
    body = {"name": a.name, "imageName": a.image, "gpuTypeIds": gpus, "gpuCount": 1, "containerDiskInGb": a.disk, "volumeInGb": 0,
            "cloudType": a.cloud, "computeType": "GPU", "ports": a.ports.split(",")}
    script = f"wget -qO- '{a.url}' | bash" if a.raw else f"(wget -qO- '{a.url}' | bash &) ; /start.sh"
    if a.entrypoint:
        body["dockerEntrypoint"] = ["bash", "-c"]
        body["dockerStartCmd"] = [script]
    else:
        body["dockerStartCmd"] = ["bash", "-c", script]
    st, out = call("POST", "/pods", body)
    if st >= 300:
        sys.exit(f"HTTP {st}: {out}")
    pid = out.get("id") if isinstance(out, dict) else out
    print("created", pid, "->", f"https://{pid}-8000.proxy.runpod.net/run.log")
elif cmd == "get":
    st, out = call("GET", f"/pods/{sys.argv[2]}")
    print(json.dumps({k: out.get(k) for k in ("id", "name", "desiredStatus", "publicIp", "portMappings", "costPerHr")}, indent=1) if st == 200 else f"HTTP {st}: {out}")
elif cmd in ("terminate", "stop"):
    pid = sys.argv[2]
    st, out = call("DELETE" if cmd == "terminate" else "POST", f"/pods/{pid}" + ("" if cmd == "terminate" else "/stop"))
    print(cmd, pid, "->", st, out if st >= 300 else "ok")
else:
    sys.exit("unknown command")
