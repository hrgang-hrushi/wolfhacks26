"""Rent, drive and tear down one vast.ai GPU box for the vision runs.

    python scripts/cloud/box.py offers            # list boxes that pass the filter
    python scripts/cloud/box.py rent --offer ID   # rent one (refused if the money left does not cover an hour)
    python scripts/cloud/box.py selfstop-test     # prove the box can stop itself, then arm the deadline watcher
    python scripts/cloud/box.py push | setup | memcheck
    python scripts/cloud/box.py run NAME "command" ; python scripts/cloud/box.py wait NAME
    python scripts/cloud/box.py pull REMOTE_DIR LOCAL_DIR
    python scripts/cloud/box.py stop | start | status | teardown

Money: one cap for the whole campaign (CAP_USD), counted across every box rented, replacements and
stopped time included. The deadline is fixed when a box is rented and a watcher on the box stops it
at that time without this machine. State lives in logs/cloud_box_state.json, closed rentals in
logs/cloud_box_history.json. Standard library only; every vast.ai and ssh call goes through _sh.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"
STATE = LOGS / "cloud_box_state.json"
HISTORY = LOGS / "cloud_box_history.json"
KNOWN_HOSTS = LOGS / "cloud_known_hosts"
REMOTE = "/root/hack"

CAP_USD = 15.0
MAX_HOURS = 8.0
MAX_REPLACEMENTS = 2
RESERVE_MIN = 20
DISK_GB = 100
BW_FREE = 0.001  # $/GB; real free hosts show rounding dust
HOURS_PER_MONTH = 730.0
EU = {"AT", "BE", "BG", "CH", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB", "GR", "HR", "HU", "IE", "IS", "IT",
      "LT", "LU", "LV", "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK", "UK"}
GPU_CHOICES = (("RTX 5090",), ("RTX 4090",))

PUSH_LIST = ["src", "tests/vision", "scripts/cloud", "pyproject.toml", "uv.lock", ".python-version",
             "data/raw/ncdot_joined.parquet", "data/raw/naip_2022_index.parquet",
             "data/processed/segments_targets.parquet"]
OPTIONAL_PUSH = {"data/processed/segments_targets.parquet"}
CODE_DIRS = ("src", "tests/vision", "scripts/cloud")

# PATH for non-interactive ssh sessions on the box, then the project directory
REMOTE_PREFIX = f"export PATH=/opt/conda/bin:/root/.local/bin:/usr/local/bin:$PATH; cd {REMOTE}"
# the container's own id and key live in PID 1's environment; ssh sessions do not inherit them
ENV_PREFIX = ("export $(tr '\\0' '\\n' < /proc/1/environ | grep -E '^(CONTAINER_ID|CONTAINER_API_KEY)=' | xargs) "
              "2>/dev/null; export PATH=/opt/conda/bin:/root/.local/bin:/usr/local/bin:$PATH")


class BoxError(RuntimeError):
    pass


class SelfStopUnavailable(BoxError):
    pass


class OfferGone(BoxError):
    """The offer could not be rented (usually someone else took it). Nothing was created or charged."""


def _now() -> float:
    """The clock used for every billing and state timestamp. Tests replace this."""
    return time.time()


def _sh(args, timeout=600, input=None, stdin=None, stdout=None):
    """The one place a subprocess is started. Tests replace this."""
    return subprocess.run(args, capture_output=stdout is None, text=stdout is None, timeout=timeout,
                          input=input, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE if stdout else None)


# ---------------------------------------------------------------- offers and money

def vastai_bin() -> str:
    for cand in (os.environ.get("VASTAI_BIN"), shutil.which("vastai"),
                 os.path.expanduser("~/Powerlifting-Analyzer/.venv/bin/vastai")):
        if cand and os.path.exists(cand):
            return cand
    raise BoxError("vastai CLI not found; set VASTAI_BIN")


def country(offer) -> str:
    return str(offer.get("geolocation") or "").split(",")[-1].strip().upper()


def filter_offers(offers, gpu_names=GPU_CHOICES[0], min_gpu_ram_mib=24000, max_dph=1.30, min_cores=16,
                  min_ram_gb=48, min_disk=DISK_GB, min_inet=800, min_reliability=0.98, min_cuda=13.0, n=5):
    """Up to n offers that can run the job, one per machine, European hosts first, then cheapest."""
    out, seen = [], set()
    for o in sorted(offers, key=lambda o: (country(o) not in EU, o.get("dph_total") or 9e9)):
        if not o.get("rentable") or o.get("verification") != "verified":
            continue
        if o.get("num_gpus") != 1 or o.get("gpu_name") not in gpu_names:
            continue
        if (o.get("gpu_ram") or 0) < min_gpu_ram_mib or (o.get("cuda_max_good") or 0) < min_cuda:
            continue
        if (o.get("dph_total") or 9e9) > max_dph or (o.get("cpu_cores_effective") or 0) < min_cores:
            continue
        if (o.get("cpu_ram") or 0) < min_ram_gb * 1024 or (o.get("disk_space") or 0) < min_disk:
            continue
        if (o.get("inet_down") or 0) < min_inet or (o.get("reliability2") or 0) <= min_reliability:
            continue
        if (o.get("inet_down_cost") or 0) > BW_FREE or (o.get("inet_up_cost") or 0) > BW_FREE:
            continue
        if o.get("machine_id") in seen:
            continue
        seen.add(o.get("machine_id"))
        out.append(o)
        if len(out) >= n:
            break
    if not out:
        raise ValueError("no offers matched")
    return out


def allowed_hours(dph: float, cap_left: float) -> float:
    return max(0.0, min(MAX_HOURS, cap_left / dph))


def budget_ok(dph: float, cap_left: float) -> bool:
    """A box is worth renting only if the money left pays for at least an hour of it."""
    return allowed_hours(dph, cap_left) >= 1.0


def storage_rate(offer) -> float:
    return float(offer.get("storage_cost") or 0.0) * DISK_GB / HOURS_PER_MONTH


def _load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path)


def load_state():
    return _load(STATE, None)


def save_state(state) -> None:
    _save(STATE, state)


def load_history():
    return _load(HISTORY, [])


def rental_cost(rental, now: float) -> float:
    return sum(((iv["end"] or now) - iv["start"]) / 3600.0 * iv["rate"] for iv in rental["intervals"])


def spent_total(now: float, state=None, history=None) -> float:
    state = load_state() if state is None else state
    history = load_history() if history is None else history
    return sum(rental_cost(r, now) for r in history) + (rental_cost(state, now) if state else 0.0)


def cap_left(now: float, state=None, history=None) -> float:
    return CAP_USD - spent_total(now, state, history)


def new_rental(instance_id, dph, storage, now, money_left):
    return {"instance_id": instance_id, "dph": dph, "storage_rate": storage, "rented_at": now,
            "deadline_epoch": now + allowed_hours(dph, money_left) * 3600.0, "ssh_host": None, "ssh_port": None,
            "jobs": {}, "last_run_at": 0.0, "last_verified_pull_at": 0.0, "watchdog_armed": False,
            "intervals": [{"start": now, "end": None, "rate": dph}]}


def switch_rate(state, rate: float, now: float) -> None:
    state["intervals"][-1]["end"] = now
    state["intervals"].append({"start": now, "end": None, "rate": rate})


def close_rental(state, reason: str, now: float) -> None:
    state["intervals"][-1]["end"] = now
    state["closed_reason"] = reason
    history = load_history()
    history.append(state)
    _save(HISTORY, history)
    if STATE.exists():
        STATE.unlink()


def abandoned_count(history=None) -> int:
    history = load_history() if history is None else history
    return sum(1 for r in history if r.get("closed_reason") != "done")


# ---------------------------------------------------------------- vast.ai

def vast(*args, input=None, timeout=120) -> str:
    r = _sh([vastai_bin(), *args], timeout=timeout, input=input)
    if r.returncode != 0:
        raise BoxError(f"vastai {' '.join(args[:3])} failed: {(r.stderr or r.stdout or '')[-300:]}")
    return r.stdout


def instances():
    data = json.loads(vast("show", "instances-v1", "--raw"))
    return data.get("instances", data) if isinstance(data, dict) else data


def instance(instance_id):
    return next((i for i in instances() if i.get("id") == instance_id), None)


def wait_status(instance_id, want_running: bool, timeout_s: float, poll_s: float = 15, sleep=time.sleep):
    """Poll until the instance is (or stops being) 'running'. Returns the instance record, or None on timeout."""
    waited = 0.0
    while waited <= timeout_s:
        inst = instance(instance_id)
        running = bool(inst) and inst.get("actual_status") == "running"
        if running == want_running and inst is not None:
            return inst
        sleep(poll_s)
        waited += poll_s
    return None


def search_offers(gpu_names):
    name = gpu_names[0].replace(" ", "_")
    q = f"gpu_name={name} rentable=true verified=true num_gpus=1 dph<1.6 disk_space>={DISK_GB}"
    return json.loads(vast("search", "offers", q, "-o", "dph", "--raw"))


def pick_offers(n=5):
    for names in GPU_CHOICES:
        try:
            return filter_offers(search_offers(names), gpu_names=names, n=n)
        except ValueError:
            continue
    raise ValueError("no offers matched for any allowed GPU")


def destroy(instance_id, sleep=time.sleep) -> None:
    vast("destroy", "instance", str(instance_id), input="y\n")
    for _ in range(3):
        if instance(instance_id) is None:
            return
        sleep(10)
    raise BoxError(f"instance {instance_id} is still listed after destroy; check the vast.ai console")


def abandon(reason: str, now=None, sleep=time.sleep) -> None:
    """Destroy the current box and book its cost. For failure paths where the box holds nothing of value."""
    state = load_state()
    if not state:
        return
    destroy(state["instance_id"], sleep=sleep)
    close_rental(state, reason, _now() if now is None else now)
    print(f"abandoned instance {state['instance_id']}: {reason}")


HIGH_PORT_PROBES = (("portquiz.net", 30776), ("portquiz.net", 41022), ("ssh7.vast.ai", 30776), ("ssh4.vast.ai", 41022))
LABEL = "image-augmentation"


def high_ports_reachable(probes=HIGH_PORT_PROBES, timeout=5.0) -> bool:
    """Whether this network lets connections out on high-numbered ports, which is where vast.ai puts ssh.

    A connection or an outright refusal both mean the path is open; only silence (a timeout) means a
    firewall is dropping it. Some venue networks allow 22, 80 and 443 and drop everything else.
    """
    import socket
    for host, port in probes:
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return True
        except ConnectionRefusedError:
            return True
        except OSError:
            continue
    return False


def rent(offer, now=None, sleep=time.sleep):
    now = _now() if now is None else now
    if load_state():
        raise BoxError("a box is already rented; teardown first")
    if not high_ports_reachable():
        raise BoxError("this network blocks outgoing connections on high ports, so a rented box would be "
                       "unreachable; switch network (hotspot, VPN) before renting")
    if abandoned_count() > MAX_REPLACEMENTS:
        raise BoxError(f"{abandoned_count()} boxes already abandoned; no further replacement without asking")
    money = cap_left(now)
    dph = float(offer["dph_total"])
    if not budget_ok(dph, money):
        raise BoxError(f"${money:.2f} left does not cover an hour at ${dph:.2f}/h")
    try:
        out = json.loads(vast("create", "instance", str(offer["id"]), "--image", "pytorch/pytorch",
                              "--disk", str(DISK_GB), "--ssh", "--raw"))
        contract = out["new_contract"]
    except (BoxError, ValueError, KeyError) as e:
        raise OfferGone(f"offer {offer['id']} could not be rented: {e}") from e
    state = new_rental(contract, dph, storage_rate(offer), now, money)
    save_state(state)  # before anything else can fail
    try:  # a name in the console, so other sessions on this account leave it alone
        vast("label", "instance", str(contract), LABEL)
    except BoxError:
        pass
    inst = wait_status(state["instance_id"], True, 900, sleep=sleep)
    if inst is None:
        abandon("never reached running", sleep=sleep)
        raise BoxError("instance never reached running; destroyed")
    refresh_ssh(state, inst)
    try:
        ssh("true")
    except BoxError:
        abandon("ssh unreachable", sleep=sleep)
        raise
    return state


def rent_first(picks, only=None, sleep=time.sleep):
    """Rent the first offer in picks that is still there. Offers vanish between listing and renting."""
    picks = [o for o in picks if only is None or o["id"] == only]
    for o in picks:
        try:
            return rent(o, sleep=sleep)
        except OfferGone as e:
            print(e)
    raise BoxError("none of the listed offers could be rented")


def refresh_ssh(state, inst=None) -> None:
    inst = inst or instance(state["instance_id"])
    state["ssh_host"], state["ssh_port"] = inst.get("ssh_host"), inst.get("ssh_port")
    if KNOWN_HOSTS.exists():
        KNOWN_HOSTS.unlink()
    save_state(state)


# ---------------------------------------------------------------- ssh

def ssh_args(state):
    return ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
            "-o", "ConnectTimeout=25", "-o", "BatchMode=yes", "-o", "LogLevel=ERROR",
            "-p", str(state["ssh_port"]), f"root@{state['ssh_host']}"]


def ssh(cmd: str, retries=5, backoff=15, timeout=600, input=None, check=True, sleep=time.sleep, state=None):
    """Run cmd on the box. A connection failure (exit 255) is retried; a failing command is not."""
    state = state or load_state()
    if not state:
        raise BoxError("no box is rented")
    LOGS.mkdir(parents=True, exist_ok=True)
    r = None
    for attempt in range(retries):
        r = _sh(ssh_args(state) + [cmd], timeout=timeout, input=input)
        if r.returncode != 255:
            break
        if attempt < retries - 1:
            sleep(backoff)
    if r.returncode == 255:
        raise BoxError(f"ssh failed {retries} times: {(r.stderr or '')[-200:]}")
    if check and r.returncode != 0:
        raise BoxError(f"remote command failed ({r.returncode}): {cmd[:120]}\n{(r.stderr or r.stdout or '')[-500:]}")
    return r


# ---------------------------------------------------------------- self-stop and watchdog

def selfstop_test(sleep=time.sleep):
    """Stop the box from inside with its own key, watch it stop, restart it, arm the watcher."""
    state = load_state()
    probe = ssh(f"{ENV_PREFIX}; test -n \"$CONTAINER_ID\" && test -n \"$CONTAINER_API_KEY\" && echo HAVE_KEY",
                check=False)
    if "HAVE_KEY" not in (probe.stdout or ""):
        abandon("no self-stop", sleep=sleep)
        raise SelfStopUnavailable("the box has no instance key; it cannot stop itself")
    ssh(f"{ENV_PREFIX}; pip install -q vastai 2>&1 | tail -1; "
        "(sleep 2; vastai stop instance $CONTAINER_ID --api-key $CONTAINER_API_KEY) > /root/selfstop.log 2>&1 &",
        check=False)
    if wait_status(state["instance_id"], False, 180, poll_s=10, sleep=sleep) is None:
        abandon("no self-stop", sleep=sleep)
        raise SelfStopUnavailable("the box did not stop itself within 3 minutes")
    switch_rate(state, state["storage_rate"], _now())
    save_state(state)
    vast("start", "instance", str(state["instance_id"]))
    inst = wait_status(state["instance_id"], True, 600, sleep=sleep)
    if inst is None:
        abandon("restart failed", sleep=sleep)
        raise BoxError("the box did not restart after the self-stop test; destroyed")
    switch_rate(state, state["dph"], _now())
    refresh_ssh(state, inst)
    arm_watchdog()
    return state


def watchdog_script(deadline_epoch: float) -> str:
    return (f"{ENV_PREFIX}\n"
            f"while [ $(date +%s) -lt {int(deadline_epoch)} ]; do sleep 30; done\n"
            "pkill -f 'src\\.(model|pipeline)'\n"
            "touch /root/DEADLINE_HIT\n"
            "vastai stop instance $CONTAINER_ID --api-key $CONTAINER_API_KEY\n")


def arm_watchdog() -> None:
    state = load_state()
    ssh("cat > /root/watchdog.sh", input=watchdog_script(state["deadline_epoch"]))
    ssh("setsid nohup sh /root/watchdog.sh > /root/watchdog.log 2>&1 < /dev/null & echo $! > /root/watchdog.pid")
    if not watchdog_alive():
        raise BoxError("the deadline watcher did not start")
    state["watchdog_armed"] = True
    save_state(state)


def watchdog_alive() -> bool:
    r = ssh("kill -0 $(cat /root/watchdog.pid 2>/dev/null) 2>/dev/null && echo ALIVE", check=False)
    return "ALIVE" in (r.stdout or "")


def stop(now=None, sleep=time.sleep) -> None:
    state = load_state()
    vast("stop", "instance", str(state["instance_id"]))
    if wait_status(state["instance_id"], False, 180, poll_s=10, sleep=sleep) is None:
        raise BoxError("the box did not stop; check the vast.ai console")
    switch_rate(state, state["storage_rate"], _now() if now is None else now)
    state["watchdog_armed"] = False
    save_state(state)


def start(now=None, sleep=time.sleep) -> None:
    state = load_state()
    vast("start", "instance", str(state["instance_id"]))
    inst = wait_status(state["instance_id"], True, 600, sleep=sleep)
    if inst is None:
        abandon("restart failed", sleep=sleep)
        raise BoxError("the box could not restart within 10 minutes; destroyed")
    switch_rate(state, state["dph"], _now() if now is None else now)
    refresh_ssh(state, inst)
    arm_watchdog()


# ---------------------------------------------------------------- shipping code

def _skip(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix == ".pyc" or bool(re.search(r" \d+(\.[^/]*)?$", path.name))


def bundle_files(root: Path = ROOT):
    """Relative paths to send, in sorted order. Missing optional inputs are left out; a missing required one raises."""
    files = []
    for entry in PUSH_LIST:
        p = root / entry
        if not p.exists():
            if entry in OPTIONAL_PUSH:
                continue
            raise BoxError(f"missing {entry}")
        found = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
        files += [f.relative_to(root).as_posix() for f in found if not _skip(f)]
    return sorted(set(files))


_KEY_NAMES = re.compile(r"(^|/)(vast_api_key|\.env|id_[^/]*|[^/]*\.pem)$")
_KEY_TEXT = re.compile("|".join(["secret_access" + r"_key\s*=", "BEGIN [A-Z ]*PRIVATE" + " KEY",
                                 "api" + r"_key\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{24,}"]))
_TEXT_SUFFIXES = {".py", ".toml", ".lock", ".json", ".md", ".txt", ".sh", ".cfg", ".ini", ".yaml", ".yml", ""}


def scan_for_keys(files, root: Path = ROOT) -> None:
    bad = []
    for rel in files:
        if _KEY_NAMES.search(rel):
            bad.append(rel)
            continue
        p = root / rel
        if p.suffix in _TEXT_SUFFIXES and p.stat().st_size < 5_000_000:
            if _KEY_TEXT.search(p.read_text(errors="ignore")):
                bad.append(rel)
    if bad:
        raise BoxError(f"refusing to send files that look like they hold a key: {bad}")


def code_hash(root: Path = ROOT) -> str:
    """Fingerprint of the code that produced a result: every .py under CODE_DIRS plus uv.lock."""
    files = sorted(f for d in CODE_DIRS for f in (root / d).rglob("*.py") if not _skip(f))
    lock = root / "uv.lock"
    h = hashlib.sha256()
    for f in files + ([lock] if lock.exists() else []):
        h.update(f.relative_to(root).as_posix().encode())
        h.update(hashlib.sha256(f.read_bytes()).hexdigest().encode())
    return h.hexdigest()


def push(extra=()) -> str:
    files = bundle_files() + [e for e in extra]
    scan_for_keys(files)
    LOGS.mkdir(parents=True, exist_ok=True)
    tar_path = LOGS / "cloud_push.tar"
    with tarfile.open(tar_path, "w", dereference=True) as tar:  # dereference: data/ is a link in a worktree
        for rel in files:
            tar.add(ROOT / rel, arcname=rel)
    digest = code_hash()
    with open(tar_path, "rb") as f:
        _push_stream(f)
    ssh(f"echo {digest} > {REMOTE}/CODE_HASH")
    tar_path.unlink()
    return digest


def _push_stream(fileobj) -> None:
    state = load_state()
    r = _sh(ssh_args(state) + [f"mkdir -p {REMOTE}/logs && tar xf - -C {REMOTE}"], timeout=1800, stdin=fileobj)
    if r.returncode != 0:
        raise BoxError(f"push failed: {(r.stderr or '')[-300:]}")


def setup() -> str:
    ssh(f"{REMOTE_PREFIX} && pip install -q uv 2>&1 | tail -1; uv sync --frozen 2>&1 | tail -3", timeout=2400)
    r = ssh(f"{REMOTE_PREFIX} && uv run python -c \"import torch; assert torch.cuda.is_available(); "
            "print('GPU', torch.cuda.get_device_name(0))\"", check=False, timeout=600)
    if r.returncode != 0 or "GPU" not in (r.stdout or ""):
        abandon("gpu check")
        raise BoxError(f"the GPU is not usable on this box; destroyed. {(r.stderr or '')[-300:]}")
    return r.stdout.strip().splitlines()[-1]


MEMCHECK_PY = """
import torch
from src.model.train_vit import Net, dev
assert dev == "cuda"
net = Net().to(dev)
opt = torch.optim.AdamW(net.parameters(), lr=1e-5)
x = torch.rand(128, 3, 126, 126, device=dev)
with torch.autocast(dev):
    out = net(x).float()
out.abs().mean().backward(); opt.step()
net.eval()
with torch.no_grad(), torch.autocast(dev):
    net(torch.rand(512, 3, 126, 126, device=dev), True)
print("MEMCHECK_OK peak_gb=%.2f" % (torch.cuda.max_memory_allocated() / 2**30))
"""


def memcheck() -> str:
    ssh(f"cat > {REMOTE}/logs/memcheck.py", input=MEMCHECK_PY)
    r = ssh(f"{REMOTE_PREFIX} && uv run python logs/memcheck.py", check=False, timeout=900)
    if "MEMCHECK_OK" not in (r.stdout or ""):
        abandon("memory check")
        raise BoxError(f"the model does not fit or run on this GPU; destroyed. {(r.stderr or '')[-400:]}")
    return [ln for ln in r.stdout.splitlines() if "MEMCHECK_OK" in ln][-1]


# ---------------------------------------------------------------- jobs

def run(name: str, cmd: str, now=None, sleep=time.sleep) -> str:
    state = load_state()
    if not watchdog_alive():
        raise BoxError("the deadline watcher is not running on the box; refusing to launch a job")
    now = _now() if now is None else now
    job = f"{name}-{datetime.fromtimestamp(now, timezone.utc).strftime('%Y%m%d%H%M%S')}"
    if job == state["jobs"].get(name):
        raise BoxError(f"job id {job} was just used; wait a second")
    inner = f"{cmd}; echo $? > logs/{job}.rc.tmp; mv logs/{job}.rc.tmp logs/{job}.rc"
    ssh(f"{REMOTE_PREFIX} && mkdir -p logs && (setsid nohup sh -c {shlex.quote(inner)} > logs/{job}.log 2>&1 "
        f"< /dev/null & echo $! > logs/{job}.pid)")
    sleep(3)
    r = ssh(f"cd {REMOTE} && (test -f logs/{job}.rc || kill -0 $(cat logs/{job}.pid) 2>/dev/null) && echo LAUNCHED",
            check=False)
    if "LAUNCHED" not in (r.stdout or ""):
        raise BoxError(f"job {job} did not start")
    state["jobs"][name] = job
    state["last_run_at"] = now
    save_state(state)
    return job


def job_status(name: str):
    """(exit code or None while running, last lines of the log) for the current execution of name."""
    state = load_state()
    job = state["jobs"].get(name)
    if not job:
        raise BoxError(f"no job named {name} has been launched")
    r = ssh(f"cd {REMOTE} && echo RC=$(cat logs/{job}.rc 2>/dev/null) && tail -n 4 logs/{job}.log", check=False)
    out = r.stdout or ""
    m = re.search(r"^RC=(-?\d+)\s*$", out, re.M)
    return (int(m.group(1)) if m else None), out.split("\n", 1)[-1]


def wait(name: str, poll_s=30, timeout_s=3600, sleep=time.sleep) -> int:
    waited = 0.0
    while waited <= timeout_s:
        rc, tail = job_status(name)
        if rc is not None:
            print(tail.rstrip())
            return rc
        print(f"[{name}] running... {tail.strip().splitlines()[-1] if tail.strip() else ''}", flush=True)
        sleep(poll_s)
        waited += poll_s
    raise BoxError(f"job {name} still running after {timeout_s}s")


MANIFEST_PY = ("import hashlib,json,os,sys\nroot=sys.argv[1]\nout=[]\n"
               "for d,_,fs in os.walk(root):\n"
               "    for f in fs:\n"
               "        p=os.path.join(d,f); h=hashlib.sha256()\n"
               "        with open(p,'rb') as fh:\n"
               "            for b in iter(lambda: fh.read(1<<20), b''): h.update(b)\n"
               "        out.append([os.path.relpath(p,root), os.path.getsize(p), h.hexdigest()])\n"
               "print(json.dumps(sorted(out)))\n")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_manifest(manifest, directory: Path):
    """Names of files under directory that are missing, extra, or differ in size or hash from the manifest."""
    want = {rel: (size, sha) for rel, size, sha in manifest}
    have = {f.relative_to(directory).as_posix() for f in directory.rglob("*") if f.is_file()}
    bad = sorted(set(want) ^ have)
    for rel in sorted(set(want) & have):
        p = directory / rel
        if p.stat().st_size != want[rel][0] or file_sha256(p) != want[rel][1]:
            bad.append(rel)
    return bad


def pull(remote_dir: str, local_dir: Path, no_overwrite=False, now=None) -> int:
    """Copy remote_dir (relative to the project on the box) into local_dir, checked file by file."""
    state = load_state()
    local_dir = Path(local_dir).resolve()
    local_dir.mkdir(parents=True, exist_ok=True)
    r = ssh(f"cd {REMOTE} && python3 - {shlex.quote(remote_dir)}", input=MANIFEST_PY, timeout=1800)
    manifest = json.loads(r.stdout.strip().splitlines()[-1])
    incoming = local_dir / f".incoming-{int(time.time())}"
    incoming.mkdir()
    tar_path = incoming.with_suffix(".tar")
    with open(tar_path, "wb") as f:
        r = _sh(ssh_args(state) + [f"tar cf - -C {REMOTE}/{remote_dir} ."], timeout=3600, stdout=f)
    if r.returncode != 0:
        raise BoxError(f"pull failed: {(r.stderr or b'')[-300:]}")
    with tarfile.open(tar_path) as tar:
        tar.extractall(incoming, filter="data")
    tar_path.unlink()
    bad = verify_manifest(manifest, incoming)
    if bad:
        raise BoxError(f"pulled files do not match the box's list ({len(bad)}): {bad[:5]}; left in {incoming}")
    moved = 0
    for rel, _, _ in manifest:
        dest = local_dir / rel
        if no_overwrite and dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(incoming / rel, dest)
        moved += 1
    shutil.rmtree(incoming)
    state = load_state()
    state["last_verified_pull_at"] = _now() if now is None else now
    save_state(state)
    return moved


# ---------------------------------------------------------------- photo checks

DIGEST_PY = ("import glob,hashlib,os,sys\nimport numpy as np\n"
             "for f in sorted(glob.glob(os.path.join(sys.argv[1], '*.npy'))):\n"
             "    print(os.path.basename(f), hashlib.sha256(np.load(f).tobytes()).hexdigest())\n")


def parse_digests(text: str) -> dict:
    return dict(ln.split() for ln in text.splitlines() if len(ln.split()) == 2 and ln.split()[0].endswith(".npy"))


def compare_digests(a: dict, b: dict, names=None):
    """Names whose pixel hash differs, or that are missing on either side. names limits the check."""
    names = sorted(set(a) | set(b)) if names is None else sorted(names)
    return [n for n in names if a.get(n) is None or a.get(n) != b.get(n)]


_BANNER = re.compile(r"([\d,]+) chips to cut from ([\d,]+) NAIP tiles with \d+ workers"
                     r"(?: \(([\d,]+) midpoints outside NAIP \d+ coverage\))?")
_FINAL = re.compile(r"\[chips\] ([\d,]+)/([\d,]+) \([\d.]+%\)\s+[\d.]+ chips/s\s+(\d+) failed\s+done in ([\d.]+)s")


def _num(s) -> int:
    return int(s.replace(",", "")) if s else 0


def parse_chips_log(text: str) -> dict:
    banner, finals = _BANNER.search(text), _FINAL.findall(text)
    if not banner:
        raise BoxError("no chips banner in the log")
    out = {"to_cut": _num(banner.group(1)), "uncovered": _num(banner.group(3)), "done": 0, "failed": 0, "seconds": 0.0}
    if finals:
        done, _, failed, seconds = finals[-1]
        out.update(done=_num(done), failed=int(failed), seconds=float(seconds))
    elif out["to_cut"] != 0:
        raise BoxError("the chips log has no final line; the run did not finish")
    return out


def ok_rate(parsed: dict) -> float:
    """Photos successfully fetched per second."""
    return (parsed["done"] - parsed["failed"]) / parsed["seconds"] if parsed["seconds"] else 0.0


def census(n_on_disk: int, parsed: dict, total=112443, max_failed_share=0.005) -> dict:
    counted = n_on_disk + parsed["failed"] + parsed["uncovered"]
    if counted != total:
        raise BoxError(f"photo count does not add up: {n_on_disk} on disk + {parsed['failed']} failed + "
                       f"{parsed['uncovered']} not covered = {counted}, expected {total}")
    if parsed["failed"] / total > max_failed_share:
        raise BoxError(f"{parsed['failed']} failed photos is above {max_failed_share:.1%} of {total}")
    return {"on_disk": n_on_disk, "failed": parsed["failed"], "uncovered": parsed["uncovered"], "total": total}


# ---------------------------------------------------------------- status and teardown

def status(now=None) -> dict:
    now = _now() if now is None else now
    state = load_state()
    out = {"spent_total": round(spent_total(now), 2), "cap_left": round(cap_left(now), 2)}
    if state:
        out.update(instance_id=state["instance_id"], dph=state["dph"],
                   hours_used=round((now - state["rented_at"]) / 3600, 2),
                   minutes_to_deadline=round((state["deadline_epoch"] - now) / 60, 1),
                   watchdog_armed=state["watchdog_armed"], jobs=state["jobs"])
    return out


def teardown(force_discard=False, now=None, sleep=time.sleep) -> float:
    state = load_state()
    if not state:
        raise BoxError("no box is rented")
    if not force_discard and not state["last_verified_pull_at"] > state["last_run_at"]:
        raise BoxError("results have not been pulled and verified since the last job; pull first or force")
    destroy(state["instance_id"], sleep=sleep)
    now = _now() if now is None else now
    close_rental(state, "done", now)
    total = spent_total(now)
    print(f"destroyed instance {state['instance_id']}; campaign spend ${total:.2f} of ${CAP_USD:.2f}")
    return total


# ---------------------------------------------------------------- CLI

def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("offers")
    p = sub.add_parser("rent"); p.add_argument("--offer", type=int, default=None, help="default: first that passes")
    for name in ("selfstop-test", "push", "setup", "memcheck", "stop", "start", "status"):
        sub.add_parser(name)
    p = sub.add_parser("ssh"); p.add_argument("command")
    p = sub.add_parser("run"); p.add_argument("name"); p.add_argument("command")
    p = sub.add_parser("wait"); p.add_argument("name"); p.add_argument("--timeout", type=float, default=3600)
    p.add_argument("--poll", type=float, default=30)
    p = sub.add_parser("job"); p.add_argument("name")
    p = sub.add_parser("pull"); p.add_argument("remote_dir"); p.add_argument("local_dir")
    p.add_argument("--no-overwrite", action="store_true")
    p = sub.add_parser("abandon"); p.add_argument("reason")
    p = sub.add_parser("teardown"); p.add_argument("--force-discard", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "offers":
        for o in pick_offers():
            print(f"{o['id']} ${o['dph_total']:.3f}/h {o['gpu_name']} {o['cpu_cores_effective']:.0f}c "
                  f"{o['cpu_ram'] / 1024:.0f}GB {o['inet_down']:.0f}Mbps {o['geolocation']} cuda {o['cuda_max_good']}")
    elif a.cmd == "rent":
        s = rent_first(pick_offers(n=20), only=a.offer)
        print(f"rented instance {s['instance_id']} at ${s['dph']:.3f}/h; deadline "
              f"{datetime.fromtimestamp(s['deadline_epoch']).strftime('%H:%M')} local")
    elif a.cmd == "selfstop-test":
        selfstop_test(); print("self-stop works; deadline watcher armed")
    elif a.cmd == "push":
        print("pushed; code hash", push())
    elif a.cmd == "setup":
        print(setup())
    elif a.cmd == "memcheck":
        print(memcheck())
    elif a.cmd == "ssh":
        r = ssh(a.command, check=False, timeout=1800); sys.stdout.write(r.stdout or ""); sys.stderr.write(r.stderr or "")
        sys.exit(r.returncode)
    elif a.cmd == "run":
        print("launched", run(a.name, a.command))
    elif a.cmd == "wait":
        sys.exit(wait(a.name, poll_s=a.poll, timeout_s=a.timeout))
    elif a.cmd == "job":
        rc, tail = job_status(a.name); print(f"exit={rc}\n{tail.rstrip()}")
    elif a.cmd == "pull":
        print("moved", pull(a.remote_dir, Path(a.local_dir), no_overwrite=a.no_overwrite), "files")
    elif a.cmd == "stop":
        stop(); print("stopped (storage-only billing)")
    elif a.cmd == "start":
        start(); print("running; deadline watcher re-armed")
    elif a.cmd == "status":
        print(json.dumps(status(), indent=1))
    elif a.cmd == "abandon":
        abandon(a.reason)
    elif a.cmd == "teardown":
        teardown(force_discard=a.force_discard)


if __name__ == "__main__":
    main()
