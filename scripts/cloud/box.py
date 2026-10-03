"""Rent, drive and tear down one vast.ai GPU box for the vision runs.

    python scripts/cloud/box.py offers            # list boxes that pass the filter
    python scripts/cloud/box.py rent              # rent the first that is still there
    python scripts/cloud/box.py selfstop-test     # prove the box can stop itself, then check the deadline watcher
    python scripts/cloud/box.py push | setup | memcheck
    python scripts/cloud/box.py identity | trial  # the photo checks before the full fetch
    python scripts/cloud/box.py run NAME "command" ; python scripts/cloud/box.py wait NAME
    python scripts/cloud/box.py census            # the fetch contract
    python scripts/cloud/box.py pull REMOTE_DIR LOCAL_DIR
    python scripts/cloud/box.py stop | start | status | teardown

Money: one cap for the whole campaign (CAP_USD), counted across every box rented, replacements and
stopped time included. The deadline is fixed when a box is rented; a watcher installed by the box's
own start-up script stops the box at that time without this machine. Every action targets the one
instance id this driver created. State and the spend history live outside the repository
(~/.config/hack-ncsu-cloud, or $BOX_STATE_DIR) so the cap holds from any checkout. Standard library
only; every vast.ai and ssh call goes through _sh.
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
STATE_DIR = Path(os.environ.get("BOX_STATE_DIR") or Path.home() / ".config" / "hack-ncsu-cloud")
STATE = STATE_DIR / "cloud_box_state.json"
HISTORY = STATE_DIR / "cloud_box_history.json"
KNOWN_HOSTS = LOGS / "cloud_known_hosts"
REMOTE = "/root/hack"
RESULTS_DIR = "data/processed/vision"
CHIPS_DIR = "data/chips"

CAP_USD = 15.0
MAX_HOURS = 8.0
MAX_REPLACEMENTS = 2
DISK_GB = 100
BW_FREE = 0.001  # $/GB; real free hosts show rounding dust
HOURS_PER_MONTH = 730.0
MIN_PHOTO_RATE = 20.0  # photos a second; below this the statewide fetch is not worth starting
PRICE_MARGIN = 1.10    # the billed price may exceed the offer's by this much before the box is refused
TOTAL_SEGMENTS = 112_443
IDENTITY_MIN = 45      # of the 50 photos this machine holds, how many must also be on the box to call them identical
TRIAL_MIN = 400        # a 500-photo trial that had fewer than this left to fetch measured nothing
LABEL = "image-augmentation"
EU = {"AT", "BE", "BG", "CH", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB", "GR", "HR", "HU", "IE", "IS", "IT",
      "LT", "LU", "LV", "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK", "UK"}
GPU_CHOICES = (("RTX 5090",), ("RTX 4090",))
HIGH_PORT_PROBES = (("portquiz.net", 30776), ("portquiz.net", 41022), ("ssh7.vast.ai", 30776), ("ssh4.vast.ai", 41022))

PUSH_LIST = ["src", "tests/vision", "scripts/cloud", "pyproject.toml", "uv.lock", ".python-version",
             "data/raw/ncdot_joined.parquet", "data/raw/naip_2022_index.parquet",
             "data/processed/segments_targets.parquet"]
OPTIONAL_PUSH = {"data/processed/segments_targets.parquet"}
CODE_DIRS = ("src", "tests/vision", "scripts/cloud")
PULL_ROOTS = (RESULTS_DIR, CHIPS_DIR)  # the only local folders pull may write into

# PATH for non-interactive ssh sessions on the box, then the project directory
REMOTE_PATH = "export PATH=/opt/conda/bin:/root/.local/bin:/usr/local/bin:$PATH"
REMOTE_PREFIX = f"{REMOTE_PATH}; cd {REMOTE}"
# the container's own id and key live in PID 1's environment; ssh sessions do not inherit them
ENV_PREFIX = ("export $(tr '\\0' '\\n' < /proc/1/environ | grep -E '^(CONTAINER_ID|CONTAINER_API_KEY)=' | xargs) "
              f"2>/dev/null; {REMOTE_PATH}")
_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


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


def _run(args, **kw):
    """_sh, with a hung command reported as a BoxError so every failure path sees one exception type."""
    try:
        return _sh(args, **kw)
    except subprocess.TimeoutExpired as e:
        raise BoxError(f"command timed out after {e.timeout}s: {' '.join(map(str, args[:3]))}") from e


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


# ---------------------------------------------------------------- vast.ai

def vast(*args, input=None, timeout=120) -> str:
    r = _run([vastai_bin(), *args], timeout=timeout, input=input)
    if r.returncode != 0:
        raise BoxError(f"vastai {' '.join(args[:3])} failed: {(r.stderr or r.stdout or '')[-300:]}")
    return r.stdout


def _last_json(text: str):
    """The JSON document in the CLI's output. `--raw` prints it over several lines, and warnings may come first."""
    lines = (text or "").strip().splitlines()
    for i, line in enumerate(lines):
        if line.lstrip()[:1] in ("{", "["):
            try:
                return json.loads("\n".join(lines[i:]))
            except ValueError:
                continue
    return json.loads(text)


def instances():
    out = vast("show", "instances-v1", "--raw")
    try:
        data = _last_json(out)
    except ValueError as e:
        raise BoxError(f"the instance listing could not be read: {(out or '').strip()[-200:] or 'empty output'}") from e
    return data.get("instances", data) if isinstance(data, dict) else data


def instance(instance_id):
    return next((i for i in instances() if i.get("id") == instance_id), None)


def wait_status(instance_id, want_running: bool, timeout_s: float, poll_s: float = 15, sleep=time.sleep):
    """Poll until the instance is (or stops being) 'running'. Returns its record, or None on timeout.

    A poll that fails (a dropped API call) is ridden out, not raised.
    """
    waited = 0.0
    while waited <= timeout_s:
        try:
            inst = instance(instance_id)
        except (BoxError, ValueError):
            inst = None
        if inst is not None and (inst.get("actual_status") == "running") == want_running:
            return inst
        sleep(poll_s)
        waited += poll_s
    return None


def search_offers(gpu_names):
    name = gpu_names[0].replace(" ", "_")
    q = f"gpu_name={name} rentable=true verified=true num_gpus=1 dph<1.6 disk_space>={DISK_GB}"
    # --storage: price the offer with the disk this driver actually rents (the default prices 5 GiB)
    return _last_json(vast("search", "offers", q, "-o", "dph", "--storage", str(DISK_GB), "--raw"))


def pick_offers(n=5):
    for names in GPU_CHOICES:
        try:
            return filter_offers(search_offers(names), gpu_names=names, n=n)
        except ValueError:
            continue
    raise ValueError("no offers matched for any allowed GPU")


def destroy(instance_id, sleep=time.sleep) -> None:
    """Destroy this one instance and confirm it is gone. An instance that is already gone counts as destroyed."""
    last = None
    for _ in range(3):
        try:
            vast("destroy", "instance", str(instance_id), input="y\n")
        except BoxError as e:
            last = e
        try:
            if instance(instance_id) is None:
                return
        except (BoxError, ValueError) as e:
            last = e
        sleep(10)
    raise BoxError(f"instance {instance_id} is still listed after destroy; check the vast.ai console ({last})")


def abandon(reason: str, now=None, sleep=time.sleep) -> None:
    """Destroy the current box and book its cost. For failure paths where the box holds nothing of value."""
    state = sync_billing(now)
    if not state:
        return
    destroy(state["instance_id"], sleep=sleep)
    close_rental(state, reason, _now() if now is None else now)
    print(f"abandoned instance {state['instance_id']}: {reason}")


GRACE_MIN = 20  # a box started again after its deadline gets this long to have its results copied off


def watchdog_script(deadline_epoch: float) -> str:
    """Runs on the box: wait for the fixed deadline, stop the jobs, then keep asking vast.ai to stop the box.

    The stop is repeated every minute for as long as the box is up: the vastai CLI exits 0 even when
    the API refuses, so its exit status cannot tell a stop that worked from one that did not. The
    loop ends when the box does. A start after the deadline gets GRACE_MIN minutes first, so results
    can still be copied off. No procps tools are assumed (the image may not have pkill).
    """
    return (f"{ENV_PREFIX}\n"
            f"if [ $(date +%s) -ge {int(deadline_epoch)} ]; then sleep {GRACE_MIN * 60}; fi\n"
            f"while [ $(date +%s) -lt {int(deadline_epoch)} ]; do sleep 30; done\n"
            "for p in /proc/[0-9]*; do grep -qaE 'src\\.(model|pipeline)' $p/cmdline 2>/dev/null "
            "&& kill ${p#/proc/} 2>/dev/null; done\n"
            "touch /root/DEADLINE_HIT\n"
            "command -v vastai >/dev/null 2>&1 || pip install -q vastai\n"
            "while true; do vastai stop instance $CONTAINER_ID --api-key $CONTAINER_API_KEY; sleep 60; done\n")


WATCHDOG_LAUNCH = ("setsid nohup sh /root/watchdog.sh > /root/watchdog.log 2>&1 < /dev/null & "
                   "echo $! > /root/watchdog.pid")
# alive = the recorded pid exists AND its command line is the watcher (a reused pid does not count)
WATCHDOG_ALIVE = ("p=$(cat /root/watchdog.pid 2>/dev/null); test -n \"$p\" && "
                  "grep -qa watchdog.sh /proc/$p/cmdline 2>/dev/null && echo ALIVE")


def onstart_script(deadline_epoch: float) -> str:
    """The box's start-up script: it installs and launches the watcher every time the container starts."""
    return ("#!/bin/bash\ncat > /root/watchdog.sh <<'WATCHDOG_EOF'\n" + watchdog_script(deadline_epoch)
            + "WATCHDOG_EOF\n" + WATCHDOG_LAUNCH + "\n")


def _created_id(stdout: str, before: set, sleep=time.sleep, polls=3, poll_s=5):
    """The id of the instance a create call made, or None if it made none.

    When the output cannot be read, the only instance that may be adopted is one that was not there
    before AND carries this driver's label: another session's box on the same account is never ours.
    The listing can lag, so it is polled a few times before concluding that nothing was created.
    """
    try:
        out = _last_json(stdout)
        if isinstance(out, dict) and out.get("new_contract"):
            return int(out["new_contract"])
    except ValueError:
        pass
    m = re.search(r"new_contract\D{0,5}(\d+)", stdout or "")
    if m:
        return int(m.group(1))
    readable = False
    for attempt in range(polls):
        try:
            new = {i["id"] for i in instances() if i.get("label") == LABEL} - before
            readable = True
            if new:
                return max(new)
        except (BoxError, ValueError):
            pass
        if attempt < polls - 1:
            sleep(poll_s)
    if not readable:
        raise BoxError("create returned unreadable output and the instance list could not be read; "
                       "check the vast.ai console before renting again")
    return None


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
    # The deadline is baked into the box's start-up script, so it is set from the offer price plus a
    # margin; a billed price above that margin is refused below rather than outrunning the deadline.
    deadline = now + allowed_hours(dph * PRICE_MARGIN, money) * 3600.0
    before = {i["id"] for i in instances()}
    try:
        stdout = vast("create", "instance", str(offer["id"]), "--image", "pytorch/pytorch", "--disk", str(DISK_GB),
                      "--ssh", "--label", LABEL, "--cancel-unavail", "--onstart-cmd", onstart_script(deadline), "--raw")
    except BoxError as e:
        stdout = str(e)
    contract = _created_id(stdout, before, sleep=sleep)
    if contract is None:
        raise OfferGone(f"offer {offer['id']} could not be rented: {stdout[-200:]}")
    state = new_rental(contract, dph, storage_rate(offer), now, money)
    state["deadline_epoch"] = deadline
    save_state(state)  # before anything else can fail
    try:
        inst = wait_status(contract, True, 900, sleep=sleep)
        if inst is None:
            raise BoxError("never reached running")
        billed = float(inst.get("dph_total") or 0)
        if billed > dph * PRICE_MARGIN:
            raise BoxError(f"billed ${billed:.3f}/h is more than {PRICE_MARGIN:.0%} of the ${dph:.3f}/h offered")
        if billed > state["dph"]:  # the billed price, if higher than the offer's
            state["dph"] = billed
            state["intervals"][0]["rate"] = billed
        refresh_ssh(state, inst)
        _ssh_ready(sleep=sleep)
        arm_watchdog()  # the start-up script should have launched it; confirm, and launch it if not
    except BaseException as e:  # including Ctrl-C: a box nobody is driving must not stay rented
        reason = "ssh unreachable" if "ssh failed" in str(e) else str(e)[:60] or type(e).__name__
        try:
            abandon(reason, sleep=sleep)
        except Exception as e2:
            raise BoxError(f"instance {contract} may still be running: {e2}") from e
        if isinstance(e, BoxError):
            raise BoxError(f"{e}; destroyed") from e
        raise
    return state


def _ssh_ready(sleep=time.sleep) -> None:
    ssh("true", sleep=sleep)


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
    """Run cmd on the box. A connection failure (exit 255) is retried; a failing command is not.

    ssh reports its own failures as 255, which a remote command could in principle also return, so
    commands that must not run twice (launching a job) pass retries=1.
    """
    state = state or load_state()
    if not state:
        raise BoxError("no box is rented")
    LOGS.mkdir(parents=True, exist_ok=True)
    r = None
    for attempt in range(retries):
        r = _run(ssh_args(state) + [cmd], timeout=timeout, input=input)
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

def watchdog_alive() -> bool:
    """Whether the watcher script is running on the box: its recorded pid exists and is the watcher."""
    r = ssh(WATCHDOG_ALIVE, check=False)
    return "ALIVE" in (r.stdout or "")


def arm_watchdog() -> None:
    """Make sure the watcher is running. The start-up script launches it; this covers the case where it did not."""
    state = load_state()
    script = watchdog_script(state["deadline_epoch"])
    want = hashlib.sha256(script.encode()).hexdigest()
    # The script on the box must be the text meant, byte for byte: it reaches the box inside the
    # start-up command, and a mangled copy would run happily and never be able to stop the box.
    have = (ssh("sha256sum /root/watchdog.sh 2>/dev/null | cut -d' ' -f1", check=False).stdout or "").strip()
    if have != want or not watchdog_alive():
        ssh("kill $(cat /root/watchdog.pid 2>/dev/null) 2>/dev/null; cat > /root/watchdog.sh", input=script)
        ssh(WATCHDOG_LAUNCH, retries=1)
        have = (ssh("sha256sum /root/watchdog.sh 2>/dev/null | cut -d' ' -f1", check=False).stdout or "").strip()
        if have != want:
            raise BoxError("the deadline watcher script on the box is not the one that was sent")
        if not watchdog_alive():
            raise BoxError("the deadline watcher did not start")
    state["watchdog_armed"] = True
    save_state(state)


def _arm_or_stop(sleep=time.sleep) -> None:
    """After a (re)start: the watcher must be running, or the box is stopped rather than left unwatched."""
    try:
        arm_watchdog()
    except BaseException as e:
        state = load_state()
        stopped = False
        try:  # the CLI exits 0 even when the API refuses, so the stop is confirmed by the instance's status
            vast("stop", "instance", str(state["instance_id"]))
            stopped = wait_status(state["instance_id"], False, 180, poll_s=10, sleep=sleep) is not None
        except Exception:
            pass
        if stopped:
            switch_rate(state, state["storage_rate"], _now())
            state["watchdog_armed"] = False
            save_state(state)
            raise BoxError(f"the deadline watcher could not be armed, so the box was stopped: {e}") from e
        try:
            abandon("unwatched and would not stop", sleep=sleep)
        except Exception as e2:
            raise BoxError(f"the watcher could not be armed and the box could neither be stopped nor destroyed "
                           f"(instance {state['instance_id']}): {e2}") from e
        raise BoxError(f"the deadline watcher could not be armed and the box did not stop, so it was destroyed: {e}") from e


def selfstop_test(sleep=time.sleep):
    """Stop the box from inside with its own key, watch it stop, restart it, confirm the watcher."""
    state = load_state()
    probe = ssh(f"{ENV_PREFIX}; test -n \"$CONTAINER_ID\" && test -n \"$CONTAINER_API_KEY\" && echo HAVE_KEY",
                check=False)
    if "HAVE_KEY" not in (probe.stdout or ""):
        abandon("no self-stop", sleep=sleep)
        raise SelfStopUnavailable("the box has no instance key; it cannot stop itself")
    ssh(f"{ENV_PREFIX}; command -v vastai >/dev/null 2>&1 || pip install -q vastai 2>&1 | tail -1; "
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
    _arm_or_stop(sleep=sleep)
    return load_state()


def sync_billing(now=None):
    """Book a stop the driver did not make itself. Returns the current state.

    When the watcher stops the box at the deadline, the books still show it running. Left alone they
    would bill a stopped box at the full price, overstate the spend and, in time, refuse even the
    20 minutes needed to copy results off. So: if the instance is not running while the last interval
    is at the running price, that interval ends at the deadline (or now, if earlier) and storage
    billing starts there.
    """
    state = load_state()
    if not state:
        return state
    now = _now() if now is None else now
    last = state["intervals"][-1]
    if last["end"] is None and last["rate"] == state["dph"]:
        try:
            inst = instance(state["instance_id"])
        except BoxError:
            return state  # cannot tell; leave the books as they are
        if inst is not None and inst.get("actual_status") != "running":
            # the watcher stops the box at the deadline; after a start past the deadline, GRACE_MIN minutes later
            deadline = state["deadline_epoch"]
            ran_until = last["start"] + GRACE_MIN * 60 if last["start"] >= deadline else deadline
            switch_rate(state, state["storage_rate"], max(last["start"], min(now, ran_until)))
            state["watchdog_armed"] = False
            save_state(state)
    return state


def stop(now=None, sleep=time.sleep) -> None:
    state = load_state()
    vast("stop", "instance", str(state["instance_id"]))
    if wait_status(state["instance_id"], False, 180, poll_s=10, sleep=sleep) is None:
        raise BoxError("the box did not stop; check the vast.ai console")
    switch_rate(state, state["storage_rate"], _now() if now is None else now)
    state["watchdog_armed"] = False
    save_state(state)


def start(now=None, sleep=time.sleep, grace=False) -> None:
    """Start a stopped box. Past its deadline this is refused, except with grace: the watcher then
    gives it GRACE_MIN minutes, enough to copy results off, before stopping it again."""
    state = sync_billing()
    at = _now() if now is None else now
    if at >= state["deadline_epoch"]:
        if not grace:
            raise BoxError(f"the box is past its deadline; `start --grace` brings it up for {GRACE_MIN} minutes "
                           "to copy results off")
        if cap_left(at) < state["dph"] * GRACE_MIN / 60.0:
            raise BoxError(f"${cap_left(at):.2f} left does not cover {GRACE_MIN} more minutes at ${state['dph']:.2f}/h")
    vast("start", "instance", str(state["instance_id"]))
    inst = wait_status(state["instance_id"], True, 600, sleep=sleep)
    if inst is None:
        if grace or state["jobs"]:
            # A stopped box is not guaranteed its GPU back. It may hold results nobody has copied yet,
            # so it is left stopped (storage billing only) rather than destroyed.
            raise BoxError("the box did not come up within 10 minutes and is still stopped (storage billing only); "
                           "try `start` again later, or `teardown --force-discard` to give up what is on it")
        abandon("restart failed", sleep=sleep)
        raise BoxError("the box could not restart within 10 minutes; destroyed")
    switch_rate(state, state["dph"], _now() if now is None else now)
    refresh_ssh(state, inst)
    _arm_or_stop(sleep=sleep)


# ---------------------------------------------------------------- shipping code

def _skip(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix == ".pyc" or bool(re.search(r" \d+(\.[^/]*)?$", path.name))


def bundle_files(root=None):
    """Relative paths to send, in sorted order. Missing optional inputs are left out; a missing required one raises."""
    root = Path(ROOT if root is None else root)
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


# Built in pieces so this file does not match its own patterns.
_KEY_NAMES = re.compile(r"(^|/)(vast_api_key[^/]*|\.env[^/]*|id_(rsa|dsa|ecdsa|ed25519)[^/]*|[^/]*\.(pem|key|p12|pfx)|"
                        r"[^/]*credentials[^/]*|\.netrc|\.npmrc)$", re.I)
_SECRET_WORD = "(?:api[_-]?" + "key|secret[_-]?access[_-]?" + "key|secret|pass" + "word|pass" + "wd|to" + "ken)"
_SECRET_VALUE = r"[A-Za-z0-9_\-/+=.]{12,}"
_KEY_TEXT = re.compile("|".join([
    # a quoted value: API_KEY = "...", {"apiKey": "..."}
    _SECRET_WORD + r"""["']?\s*[:=]\s*["']""" + _SECRET_VALUE + r"""["']""",
    # or a bare value that ends at a delimiter: SECRET_ACCESS_KEY=... in a shell line, ?api_key=...& in a URL.
    # (`token = get_token(...)` is ordinary code and does not match: its value runs into a bracket.)
    _SECRET_WORD + r"\w*\s*[:=]\s*" + _SECRET_VALUE + r"""(?=$|[\s;&#,'"])""",
    "BEGIN [A-Z ]*PRIVATE" + " KEY",
    "gh[pousr]_" + "[A-Za-z0-9]{30,}",
    "AKIA" + "[0-9A-Z]{16}",
    "sk-" + "[A-Za-z0-9_-]{24,}",
]), re.I | re.M)
_BINARY_SUFFIXES = {".parquet", ".npy", ".png", ".jpg", ".jpeg", ".tif"}


def scan_for_keys(files, root=None) -> None:
    """Refuse a bundle with a file named like a credential, or any non-binary file whose text looks like one."""
    root = Path(ROOT if root is None else root)
    bad = []
    for rel in files:
        if _KEY_NAMES.search(rel):
            bad.append(rel)
            continue
        p = root / rel
        if p.suffix.lower() not in _BINARY_SUFFIXES and p.stat().st_size < 5_000_000:
            if _KEY_TEXT.search(p.read_text(errors="ignore")):
                bad.append(rel)
    if bad:
        raise BoxError(f"refusing to send files that look like they hold a key: {bad}")


def code_hash(root=None) -> str:
    """Fingerprint of the code that produced a result: every .py under CODE_DIRS plus uv.lock."""
    root = Path(ROOT if root is None else root)
    files = sorted(f for d in CODE_DIRS for f in (root / d).rglob("*.py") if not _skip(f))
    lock = root / "uv.lock"
    h = hashlib.sha256()
    for f in files + ([lock] if lock.exists() else []):
        h.update(f.relative_to(root).as_posix().encode())
        h.update(hashlib.sha256(f.read_bytes()).hexdigest().encode())
    return h.hexdigest()


def push(extra=()) -> str:
    files = bundle_files() + list(extra)
    scan_for_keys(files)
    LOGS.mkdir(parents=True, exist_ok=True)
    tar_path = LOGS / "cloud_push.tar"
    with tarfile.open(tar_path, "w", dereference=True) as tar:  # dereference: data/ is a link in a worktree
        for rel in files:
            tar.add(ROOT / rel, arcname=rel)
    digest = code_hash()
    try:
        with open(tar_path, "rb") as f:
            r = _run(ssh_args(load_state()) + [f"mkdir -p {REMOTE}/logs && tar xf - -C {REMOTE}"], timeout=1800, stdin=f)
        if r.returncode != 0:
            raise BoxError(f"push failed: {(r.stderr or '')[-300:]}")
    finally:
        tar_path.unlink()
    ssh(f"echo {digest} > {REMOTE}/CODE_HASH")
    return digest


def setup() -> str:
    """Install the locked environment on the box and prove the GPU works.

    A failed install raises and leaves the box up (the watcher bounds it) so the fallback install
    can be tried; a GPU that does not work destroys the box.
    """
    r = ssh(f"{REMOTE_PREFIX} && mkdir -p logs && (command -v uv >/dev/null 2>&1 || pip install -q uv) "
            "&& uv sync --frozen > logs/setup.log 2>&1", check=False, timeout=2400)
    if r.returncode != 0:
        tail = ssh(f"tail -n 15 {REMOTE}/logs/setup.log", check=False).stdout
        raise BoxError(f"the install failed on the box (exit {r.returncode}); the box is still up:\n{tail}")
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
        err = (r.stderr or "") + (r.stdout or "")
        if re.search(r"out of memory|OutOfMemoryError", err, re.I):  # only this means the GPU is too small
            abandon("memory check")
            raise BoxError(f"the model does not fit on this GPU; destroyed. {err[-400:]}")
        raise BoxError(f"the memory check could not run (the box is still up): {err[-600:]}")
    return [ln for ln in r.stdout.splitlines() if "MEMCHECK_OK" in ln][-1]


# ---------------------------------------------------------------- jobs

def _check_name(name: str) -> str:
    if not _NAME.match(name or ""):
        raise BoxError(f"job name {name!r} must be letters, digits, '-' or '_'")
    return name


def run(name: str, cmd: str, now=None, sleep=time.sleep) -> str:
    _check_name(name)
    state = load_state()
    now = _now() if now is None else now
    if now >= state["deadline_epoch"]:
        raise BoxError("the box is past its deadline; no new job is launched")
    if not watchdog_alive():
        raise BoxError("the deadline watcher is not running on the box; refusing to launch a job")
    job = f"{name}-{datetime.fromtimestamp(now, timezone.utc).strftime('%Y%m%d%H%M%S')}"
    if job == state["jobs"].get(name):
        raise BoxError(f"job id {job} was just used; wait a second")
    inner = f"{cmd}; echo $? > logs/{job}.rc.tmp; mv logs/{job}.rc.tmp logs/{job}.rc"
    ssh(f"{REMOTE_PREFIX} && mkdir -p logs && (setsid nohup sh -c {shlex.quote(inner)} > logs/{job}.log 2>&1 "
        f"< /dev/null & echo $! > logs/{job}.pid)", retries=1)  # launching twice would run the job twice
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
    return _probe(job)[::2]


def _probe(job: str):
    """(exit code or None, whether the job's process is still alive, last lines of its log)."""
    # alive = the recorded pid exists AND its command line names this job (after a restart a pid can be reused)
    r = ssh(f"cd {REMOTE} && echo RC=$(cat logs/{job}.rc 2>/dev/null) && "
            f"(p=$(cat logs/{job}.pid 2>/dev/null); test -n \"$p\" && grep -qa {job} /proc/$p/cmdline 2>/dev/null "
            f"&& echo JOB_ALIVE || echo JOB_GONE) && tail -n 4 logs/{job}.log", check=False)
    out = r.stdout or ""
    m = re.search(r"^RC=(-?\d+)\s*$", out, re.M)
    tail = "\n".join(ln for ln in out.splitlines()[1:] if ln not in ("JOB_ALIVE", "JOB_GONE"))
    return (int(m.group(1)) if m else None), "JOB_ALIVE" in out, tail


def job_state(name: str) -> str:
    """'finished', 'running', or 'died' (no exit status and no process: killed by the watcher or by a restart)."""
    job = load_state()["jobs"].get(name)
    if not job:
        raise BoxError(f"no job named {name} has been launched")
    rc, alive, _ = _probe(job)
    return "finished" if rc is not None else ("running" if alive else "died")


def job_log(name: str) -> str:
    state = load_state()
    job = state["jobs"].get(name)
    if not job:
        raise BoxError(f"no job named {name} has been launched")
    return ssh(f"cat {REMOTE}/logs/{job}.log", timeout=300).stdout


def running_jobs():
    """Names of launched jobs whose process is still alive. A job that died is not running."""
    return [name for name in load_state()["jobs"] if job_state(name) == "running"]


def wait(name: str, poll_s=30, timeout_s=3600, sleep=time.sleep) -> int:
    waited = 0.0
    while waited <= timeout_s:
        rc, tail = job_status(name)
        if rc is not None:
            print(tail.rstrip())
            return rc
        if job_state(name) == "died":
            raise BoxError(f"job {name} died without an exit status; last lines:\n{tail.rstrip()}")
        print(f"[{name}] running... {tail.strip().splitlines()[-1] if tail.strip() else ''}", flush=True)
        sleep(poll_s)
        waited += poll_s
    raise BoxError(f"job {name} still running after {timeout_s}s")


# ---------------------------------------------------------------- copying results back

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


def missing_or_different(manifest, directory: Path):
    """Files in the manifest that are absent from directory or differ in size or hash. Extra local files are fine."""
    bad = []
    for rel, size, sha in manifest:
        p = Path(directory) / rel
        if not p.is_file() or p.stat().st_size != size or file_sha256(p) != sha:
            bad.append(rel)
    return bad


def verify_manifest(manifest, directory: Path):
    """Files that are missing, different, or present locally but not in the manifest."""
    have = {f.relative_to(directory).as_posix() for f in Path(directory).rglob("*") if f.is_file()}
    return sorted(set(missing_or_different(manifest, directory)) | (have - {rel for rel, _, _ in manifest}))


def _check_remote_dir(remote_dir: str) -> str:
    p = Path(remote_dir)
    if (p.is_absolute() or ".." in p.parts or not re.match(r"^[A-Za-z0-9_./-]+$", remote_dir)
            or len(p.parts) < 2 or p.parts[0] != "data"):
        raise BoxError(f"remote folder {remote_dir!r} must be a plain path under the project's data folder")
    return remote_dir.rstrip("/")


def remote_manifest(remote_dir: str):
    """[path, size, sha256] for every file under remote_dir on the box; [] if the folder does not exist."""
    remote_dir = _check_remote_dir(remote_dir)
    r = ssh(f"{REMOTE_PREFIX} && python3 - {shlex.quote(remote_dir)}", input=MANIFEST_PY, timeout=1800)
    return _last_json(r.stdout)


def _pull_target(local_dir) -> tuple:
    """(resolved destination, whether existing files must be kept). Only the results and chips folders are allowed."""
    dest = Path(local_dir).resolve()
    for rel in PULL_ROOTS:
        allowed = (ROOT / rel).resolve()
        if dest == allowed or allowed in dest.parents:
            return dest, rel == CHIPS_DIR
    raise BoxError(f"pull may only write into {' or '.join(PULL_ROOTS)}; got {dest}")


def pull(remote_dir: str, local_dir, no_overwrite=False, now=None) -> int:
    """Copy remote_dir (relative to the project on the box) into local_dir, checked file by file.

    Results overwrite older results. In data/chips an existing file is never replaced.
    """
    remote_dir = _check_remote_dir(remote_dir)
    local_dir, keep_existing = _pull_target(local_dir)
    no_overwrite = no_overwrite or keep_existing
    state = load_state()
    manifest = remote_manifest(remote_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    incoming = local_dir / f".incoming-{int(time.time())}"
    incoming.mkdir()
    tar_path = incoming.with_suffix(".tar")
    with open(tar_path, "wb") as f:
        r = _run(ssh_args(state) + [f"tar cf - -C {shlex.quote(REMOTE + '/' + remote_dir)} ."], timeout=3600, stdout=f)
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
CHIPS_CMD = "uv run python -m src.pipeline.chips"


def parse_digests(text: str) -> dict:
    return dict(ln.split() for ln in text.splitlines() if len(ln.split()) == 2 and ln.split()[0].endswith(".npy"))


def compare_digests(a: dict, b: dict, names=None):
    """Names whose pixel hash differs, or that are missing on either side. names limits the check."""
    names = sorted(set(a) | set(b)) if names is None else sorted(names)
    return [n for n in names if a.get(n) is None or a.get(n) != b.get(n)]


def local_digests(chips_dir) -> dict:
    """Pixel hashes of the chips on this machine, computed by the same code the box runs."""
    import contextlib
    import io
    buf, argv = io.StringIO(), sys.argv
    sys.argv = ["digest", str(chips_dir)]
    try:
        with contextlib.redirect_stdout(buf):
            exec(DIGEST_PY, {})
    finally:
        sys.argv = argv
    return parse_digests(buf.getvalue())


def identity_check(local_chips_dir=None, sleep=time.sleep) -> int:
    """Fetch on the box the same 50 photos this machine has and compare pixel hashes. A mismatch destroys the box."""
    mine = local_digests(ROOT / CHIPS_DIR if local_chips_dir is None else local_chips_dir)
    if not mine:
        raise BoxError("no photos on this machine to compare against")

    def fetch_and_digest():
        ssh(f"{REMOTE_PREFIX} && {CHIPS_CMD} --limit 50 --seed 0", timeout=1800)  # skips photos already there
        return parse_digests(ssh(f"{REMOTE_PREFIX} && uv run python - {CHIPS_DIR}", input=DIGEST_PY, timeout=600).stdout)

    theirs = fetch_and_digest()
    common = sorted(set(mine) & set(theirs))
    if len(common) < IDENTITY_MIN:  # some of the 50 did not arrive: try once more before judging anything
        theirs = fetch_and_digest()
        common = sorted(set(mine) & set(theirs))
    differ = compare_digests(mine, theirs, names=common)
    if differ:  # only differing pixels condemn the box; a photo that failed to download does not
        abandon("photo identity", sleep=sleep)
        raise BoxError(f"{len(differ)} of {len(common)} photos differ between this machine and the box; destroyed: {differ[:3]}")
    if len(common) < IDENTITY_MIN:
        raise BoxError(f"only {len(common)} of the photos on this machine were fetched on the box (need {IDENTITY_MIN}); "
                       "nothing differed, the box is still up; check the fetch")
    return len(common)


def speed_trial(settings=((1, 32), (2, 64), (3, 128)), sleep=time.sleep) -> dict:
    """Three 500-photo trials. Returns the rates and the best worker count; too slow destroys the box.

    A trial that found its photos already fetched (a rerun) measures nothing, so it raises without
    touching the box.
    """
    rates = {}
    for seed, workers in settings:
        out = ssh(f"{REMOTE_PREFIX} && {CHIPS_CMD} --limit 500 --seed {seed} --workers {workers}", timeout=1800,
                  retries=1).stdout
        parsed = parse_chips_log(out)
        if parsed["to_cut"] < TRIAL_MIN:
            raise BoxError(f"the trial with seed {seed} had only {parsed['to_cut']} photos left to fetch, so it measured "
                           "nothing (was it already run?); the box is untouched")
        rates[workers] = ok_rate(parsed)
    best = max(rates, key=rates.get)
    if rates[best] < MIN_PHOTO_RATE:
        abandon("too slow", sleep=sleep)
        raise BoxError(f"best rate {rates[best]:.1f} photos/s is under {MIN_PHOTO_RATE:.0f}; destroyed. rates: {rates}")
    return {"rates": rates, "best_workers": best}


_BANNER = re.compile(r"([\d,]+) chips to cut from ([\d,]+) NAIP tiles with \d+ workers"
                     r"(?: \(([\d,]+) midpoints outside NAIP \d+ coverage\))?")
_FINAL = re.compile(r"\[chips\] ([\d,]+)/([\d,]+) \([\d.]+%\)\s+[\d.]+ chips/s\s+(\d+) failed\s+done in ([\d.]+)s")


def _num(s) -> int:
    return int(s.replace(",", "")) if s else 0


def parse_chips_log(text: str) -> dict:
    """Counts for the LAST run in the log: its banner, and its final line if it has one after that banner."""
    banners = list(_BANNER.finditer(text))
    if not banners:
        raise BoxError("no chips banner in the log")
    banner = banners[-1]
    finals = _FINAL.findall(text[banner.end():])
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


def census(n_on_disk: int, parsed: dict, total=None, max_failed_share=0.005) -> dict:
    total = TOTAL_SEGMENTS if total is None else total
    counted = n_on_disk + parsed["failed"] + parsed["uncovered"]
    if counted != total:
        raise BoxError(f"photo count does not add up: {n_on_disk} on disk + {parsed['failed']} failed + "
                       f"{parsed['uncovered']} not covered = {counted}, expected {total}")
    if parsed["failed"] / total > max_failed_share:
        raise BoxError(f"{parsed['failed']} failed photos is above {max_failed_share:.1%} of {total}")
    return {"on_disk": n_on_disk, "failed": parsed["failed"], "uncovered": parsed["uncovered"], "total": total}


def fetch_census(job: str = "fetch", sleep=time.sleep) -> dict:
    """The fetch contract on the last run of the fetch job. If the contract fails the box is stopped (photos kept).

    Asking too early, or about a job that was never launched, is just an error: it does not stop the box.
    """
    state = job_state(job)
    if state != "finished":
        raise BoxError(f"the {job} job is {'still running' if state == 'running' else 'dead without an exit status'}; "
                       "the box is untouched")
    log = job_log(job)
    n = int(ssh(f"ls {REMOTE}/{CHIPS_DIR} | grep -c '\\.npy$'", check=False).stdout.strip() or 0)
    try:
        parsed = parse_chips_log(log)
        return {**census(n, parsed), "seconds": parsed["seconds"], "rate": ok_rate(parsed)}
    except BoxError:
        stop(sleep=sleep)
        raise


COUNTY_PY = """
import os, sys
import pandas as pd
from src.pipeline.chips import chip_path
counties = sys.argv[1].split(",")
d = pd.read_parquet("data/processed/segments_targets.parquet", columns=["seg_id", "pv_COUNTY"])
out = "data/chips_counties"
os.makedirs(out, exist_ok=True)
n = 0
for seg_id in d.seg_id[d.pv_COUNTY.isin(counties)]:
    src = os.path.join("data/chips", chip_path(seg_id).name)
    dst = os.path.join(out, chip_path(seg_id).name)
    if os.path.exists(src) and not os.path.exists(dst):
        os.link(src, dst)
        n += 1
print("COUNTY_CHIPS", n)
"""


def county_chips(counties=("092-Wake", "011-Buncombe")) -> int:
    """Copy the chips of the named counties into data/chips on this machine. Existing chips are kept."""
    ssh(f"{REMOTE_PREFIX} && uv run python - {shlex.quote(','.join(counties))}", input=COUNTY_PY, timeout=900)
    return pull("data/chips_counties", ROOT / CHIPS_DIR, no_overwrite=True)


# ---------------------------------------------------------------- status and teardown

def status(now=None) -> dict:
    now = _now() if now is None else now
    state = sync_billing(now)
    out = {"spent_total": round(spent_total(now), 2), "cap_left": round(cap_left(now), 2)}
    if state:
        out.update(instance_id=state["instance_id"], dph=state["dph"],
                   hours_used=round((now - state["rented_at"]) / 3600, 2),
                   minutes_to_deadline=round((state["deadline_epoch"] - now) / 60, 1),
                   watchdog_armed=state["watchdog_armed"], jobs=state["jobs"])
    return out


def results_safe() -> None:
    """Raise unless every result on the box is on this machine, byte for byte, and no job is still running.

    A job that died (killed by the watcher at the deadline, or by a restart) is not running; what it
    left behind is still checked file by file. The box must be up for the check: a stopped box is
    started first (`start`, or `start --grace` after the deadline).
    """
    state = load_state()
    inst = instance(state["instance_id"])
    if inst is None or inst.get("actual_status") != "running":
        raise BoxError("the box is not running, so its results cannot be checked; start it (after the deadline: "
                       "`start --grace`), pull, then tear down; or use --force-discard to give up what is on it")
    still = running_jobs()
    if still:
        raise BoxError(f"jobs still running on the box: {still}")
    manifest = remote_manifest(RESULTS_DIR)
    if not manifest:
        raise BoxError("the box holds no results to keep; if that is intended, tear down with --force-discard")
    bad = missing_or_different(manifest, ROOT / RESULTS_DIR)
    if bad:
        raise BoxError(f"{len(bad)} result files on the box are not on this machine or differ: {bad[:5]}; pull first")


def teardown(force_discard=False, now=None, sleep=time.sleep) -> float:
    state = sync_billing(now)
    if not state:
        raise BoxError("no box is rented")
    if not force_discard:
        results_safe()
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
    p = sub.add_parser("rent")
    p.add_argument("--offer", type=int, default=None, help="default: first that passes")
    sub.add_parser("trial").add_argument("--seed-base", type=int, default=0,
                                         help="use other sample seeds after a partial attempt (e.g. 10 gives 11, 12, 13)")
    for name in ("offers", "selfstop-test", "push", "setup", "memcheck", "identity", "census", "county-chips",
                 "stop", "status"):
        sub.add_parser(name)
    sub.add_parser("start").add_argument("--grace", action="store_true",
                                         help=f"past the deadline: bring the box up for {GRACE_MIN} minutes to copy results")
    sub.add_parser("ssh").add_argument("command")
    p = sub.add_parser("run")
    p.add_argument("name")
    p.add_argument("command")
    p = sub.add_parser("wait")
    p.add_argument("name")
    p.add_argument("--timeout", type=float, default=3600)
    p.add_argument("--poll", type=float, default=30)
    sub.add_parser("job").add_argument("name")
    p = sub.add_parser("pull")
    p.add_argument("remote_dir")
    p.add_argument("local_dir")
    p.add_argument("--no-overwrite", action="store_true")
    sub.add_parser("abandon").add_argument("reason")
    sub.add_parser("teardown").add_argument("--force-discard", action="store_true")
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
        selfstop_test()
        print("self-stop works; deadline watcher running")
    elif a.cmd == "push":
        print("pushed; code hash", push())
    elif a.cmd == "setup":
        print(setup())
    elif a.cmd == "memcheck":
        print(memcheck())
    elif a.cmd == "identity":
        print(f"{identity_check()} photos identical on both machines")
    elif a.cmd == "trial":
        seeds = [a.seed_base + i for i in (1, 2, 3)]
        print(json.dumps(speed_trial(settings=tuple(zip(seeds, (32, 64, 128))))))
    elif a.cmd == "census":
        print(json.dumps(fetch_census()))
    elif a.cmd == "county-chips":
        print("moved", county_chips(), "chips")
    elif a.cmd == "ssh":
        r = ssh(a.command, check=False, timeout=1800)
        sys.stdout.write(r.stdout or "")
        sys.stderr.write(r.stderr or "")
        sys.exit(r.returncode)
    elif a.cmd == "run":
        print("launched", run(a.name, a.command))
    elif a.cmd == "wait":
        sys.exit(wait(a.name, poll_s=a.poll, timeout_s=a.timeout))
    elif a.cmd == "job":
        rc, tail = job_status(a.name)
        print(f"exit={rc}\n{tail.rstrip()}")
    elif a.cmd == "pull":
        print("moved", pull(a.remote_dir, Path(a.local_dir), no_overwrite=a.no_overwrite), "files")
    elif a.cmd == "stop":
        stop()
        print("stopped (storage-only billing)")
    elif a.cmd == "start":
        start(grace=a.grace)
        print("running; deadline watcher running")
    elif a.cmd == "status":
        print(json.dumps(status(), indent=1))
    elif a.cmd == "abandon":
        abandon(a.reason)
    elif a.cmd == "teardown":
        teardown(force_discard=a.force_discard)


if __name__ == "__main__":
    main()
