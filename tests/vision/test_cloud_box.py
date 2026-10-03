"""Cloud box driver (scripts/cloud/box.py). vast.ai and ssh are replaced by a small fake; nothing is rented.

The fake keeps a list of instances (the vast.ai side) and a temporary folder standing in for the
project directory on the box, so pushing, pulling, the photo checks and the teardown gate run for real
against files on disk. Like the real CLI, the fake prints its JSON over several lines and exits 0 even
when the API refuses a call. Ids C1 to C25 follow the run spec.
"""

import hashlib
import io
import json
import re
import shlex
import subprocess
import sys
import tarfile
import types

import numpy as np
import pytest

from vision_helpers import good_offer, load_box

NOSLEEP = lambda s: None  # noqa: E731


def reply(rc=0, out="", err=""):
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


def raw(obj) -> str:
    return json.dumps(obj, indent=1)  # `--raw` output spans several lines


class Fake:
    """Stands in for box._sh: a tiny vast.ai backend plus a box whose project folder is a local directory."""

    def __init__(self, box, remote):
        self.box, self.remote = box, remote
        self.calls, self.instances, self.next_id = [], {}, 5000
        self.create_status = "running"
        self.destroy_works = self.has_key = self.selfstop_works = self.start_works = True
        self.watchdog = self.launch_ok = self.gpu_ok = self.install_ok = True
        self.quiet_stop_failure = False    # the API refuses a stop; the CLI still exits 0
        self.mem_error = None              # None, "oom" or "import"
        self.destroy_errors = self.poll_errors = self.ssh_fail_times = self.listing_lag = 0
        self.warning = ""                  # text the CLI prints before its JSON
        self.create_garbled = False        # the CLI prints no usable JSON at all
        self.gone_offers = set()           # offers that someone else took
        self.stranger_on_create = False    # another session's box appears while we are renting
        self.instance_dph = None           # billed price shown on the instance record
        self.raise_on_poll = None          # an exception raised by the first status poll after create
        self.rc, self.dead, self.logs, self.offers = {}, set(), {}, []
        self.box_chips, self.box_missing = {}, []   # photos the box "fetches"; names that fail on each attempt
        self.trial_rates = {32: 40.0, 64: 80.0, 128: 60.0}
        self.trials_done = set()
        self.corrupt_pull = False
        self.on_call = None

    # ------------------------------------------------------------ dispatch
    def __call__(self, args, timeout=600, input=None, stdin=None, stdout=None):
        self.calls.append(list(args))
        if self.on_call:
            self.on_call(args)
        if args[0] == "vastai":
            return self.vast(args[1:])
        if args[0] == "ssh":
            return self.ssh(args[-1], input, stdin, stdout)
        raise AssertionError(f"unexpected command {args}")

    def created(self):
        return [c for c in self.calls if c[:3] == ["vastai", "create", "instance"]]

    def add(self, label, status="running"):
        self.next_id += 1
        self.instances[self.next_id] = {"id": self.next_id, "actual_status": status, "ssh_host": "ssh.example",
                                        "ssh_port": 2222, "label": label, "hidden_polls": 0}
        return self.next_id

    # ------------------------------------------------------------ vast.ai
    def vast(self, a):
        if a[:2] == ["show", "instances-v1"]:
            if self.raise_on_poll and self.instances:
                exc, self.raise_on_poll = self.raise_on_poll, None
                raise exc
            if self.poll_errors > 0 and self.instances:
                self.poll_errors -= 1
                return reply(err="failed with error 502: Bad Gateway")  # exit 0, nothing on stdout
            listed = []
            for inst in self.instances.values():
                if inst.get("hidden_polls", 0) > 0:
                    inst["hidden_polls"] -= 1
                else:
                    listed.append(inst)
            return reply(out=self.warning + raw({"instances": listed, "instances_found": len(listed)}))
        if a[:2] == ["create", "instance"]:
            assert "--cancel-unavail" in a
            if self.stranger_on_create:
                self.add("cctv-potholes")
            if int(a[2]) in self.gone_offers:
                return reply(err="failed with error 404: no_such_ask")  # the real CLI exits 0 here too
            new = self.add(a[a.index("--label") + 1] if "--label" in a else None, self.create_status)
            self.instances[new].update(onstart=a[a.index("--onstart-cmd") + 1], disk=a[a.index("--disk") + 1],
                                       dph_total=self.instance_dph, hidden_polls=self.listing_lag)
            if self.create_garbled:
                return reply(out="Started. (output format changed)")
            return reply(out=self.warning + raw({"success": True, "new_contract": new}))
        if a[:2] == ["destroy", "instance"]:
            if self.destroy_errors > 0:
                self.destroy_errors -= 1
                return reply(err="failed with error 503")
            if self.destroy_works:
                self.instances.pop(int(a[2]), None)
            return reply()
        if a[:2] == ["stop", "instance"]:
            if self.quiet_stop_failure:
                return reply(err="failed with error 429: Too Many Requests")
            self.instances[int(a[2])]["actual_status"] = "exited"
            return reply()
        if a[:2] == ["start", "instance"]:
            if self.start_works:
                self.instances[int(a[2])]["actual_status"] = "running"
            return reply()
        if a[:2] == ["search", "offers"]:
            return reply(out=self.warning + raw(self.offers))
        raise AssertionError(f"unexpected vastai call {a}")

    # ------------------------------------------------------------ the box
    def ssh(self, cmd, input, stdin, stdout):
        if self.ssh_fail_times > 0:
            self.ssh_fail_times -= 1
            return reply(rc=255, err="Connection refused")
        if not any(i["actual_status"] == "running" for i in self.instances.values() if i.get("label") == self.box.LABEL):
            return reply(rc=255, err="Connection refused")  # a stopped box cannot be reached
        if "echo HAVE_KEY" in cmd:
            return reply(out="HAVE_KEY\n") if self.has_key else reply(rc=1)
        if "vastai stop instance $CONTAINER_ID" in cmd:
            if self.selfstop_works:
                for inst in self.instances.values():
                    if inst.get("label") == self.box.LABEL:
                        inst["actual_status"] = "exited"
            return reply()
        if "echo ALIVE" in cmd:
            return reply(out="ALIVE\n") if self.watchdog else reply(rc=1)
        if "echo LAUNCHED" in cmd:
            return reply(out="LAUNCHED\n") if self.launch_ok else reply(rc=1)
        if "echo RC=" in cmd:
            job = re.search(r"logs/([\w\-]+)\.rc", cmd).group(1)
            code = self.rc.get(job)
            alive = "JOB_GONE" if (code is not None or job in self.dead) else "JOB_ALIVE"
            return reply(out=f"RC={'' if code is None else code}\n{alive}\nlast log line\n")
        if "tar xf - -C" in cmd:  # push
            with tarfile.open(fileobj=stdin, mode="r|") as tar:
                tar.extractall(self.remote, filter="data")
            return reply()
        if cmd.startswith("echo ") and "CODE_HASH" in cmd:
            (self.remote / "CODE_HASH").write_text(cmd.split()[1] + "\n")
            return reply()
        if "python3 - " in cmd and input == self.box.MANIFEST_PY:
            target = self.remote / cmd.rsplit("python3 - ", 1)[1].strip("'\"")
            r = subprocess.run([sys.executable, "-c", input, str(target)], capture_output=True, text=True)
            return reply(out=r.stdout)
        if cmd.startswith("tar cf - -C"):  # pull
            target = self.remote / cmd.split(" -C ", 1)[1].rsplit(" .", 1)[0].strip("'\"").replace("/root/hack/", "")
            with tarfile.open(fileobj=stdout, mode="w") as tar:
                for f in sorted(p for p in target.rglob("*") if p.is_file()):
                    data = f.read_bytes()
                    if self.corrupt_pull and f.suffix == ".json":
                        data = data[:-1] + b"X"
                    info = tarfile.TarInfo(f.relative_to(target).as_posix())
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            return types.SimpleNamespace(returncode=0, stdout=None, stderr=b"")
        if "src.pipeline.chips --limit 50 --seed 0" in cmd:
            (self.remote / "data" / "chips").mkdir(parents=True, exist_ok=True)
            missing = self.box_missing.pop(0) if self.box_missing else ()
            for name, arr in self.box_chips.items():
                if name not in missing:
                    np.save(self.remote / "data" / "chips" / name, arr)
            return reply(out="50 chips to cut from 44 NAIP tiles with 16 workers\n"
                             "[chips] 50/50 (100.0%)  9.0 chips/s  0 failed  done in 5.5s\n")
        if "src.pipeline.chips --limit 500" in cmd:
            seed, workers = (int(v) for v in re.search(r"--seed (\d+) --workers (\d+)", cmd).groups())
            if seed in self.trials_done:  # chips.py skips photos that are already on disk
                return reply(out=f"0 chips to cut from 0 NAIP tiles with {workers} workers\n")
            self.trials_done.add(seed)
            secs = 500 / self.trial_rates[workers]
            return reply(out=f"500 chips to cut from 380 NAIP tiles with {workers} workers\n"
                             f"[chips] 500/500 (100.0%)  {self.trial_rates[workers]:.1f} chips/s  0 failed  done in {secs:.1f}s\n")
        if "uv run python - data/chips" in cmd and input == self.box.DIGEST_PY:
            r = subprocess.run([sys.executable, "-c", input, str(self.remote / "data" / "chips")],
                               capture_output=True, text=True)
            return reply(out=r.stdout)
        if cmd.startswith("cat /root/hack/logs/") and cmd.endswith(".log"):
            return reply(out=self.logs.get(cmd.split("/")[-1][:-4], ""))
        if "grep -c" in cmd:
            cdir = self.remote / "data" / "chips"
            return reply(out=f"{len(list(cdir.glob('*.npy'))) if cdir.exists() else 0}\n")
        if "uv sync --frozen" in cmd:
            return reply() if self.install_ok else reply(rc=1)
        if "tail -n 15" in cmd:
            return reply(out="error: failed to build `pysheds`\n")
        if "torch.cuda.is_available()" in cmd:
            return reply(out="GPU NVIDIA GeForce RTX 5090\n") if self.gpu_ok else reply(rc=1, err="AssertionError")
        if "logs/memcheck.py" in cmd and "uv run" in cmd:
            if self.mem_error == "oom":
                return reply(rc=1, err="torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB")
            if self.mem_error == "import":
                return reply(rc=1, err="OSError: could not download vit_small_patch14_dinov2 weights")
            return reply(out="MEMCHECK_OK peak_gb=6.10\n")
        if input == self.box.COUNTY_PY:
            src, dst = self.remote / "data" / "chips", self.remote / "data" / "chips_counties"
            dst.mkdir(parents=True, exist_ok=True)
            for f in sorted(src.glob("*.npy"))[:3]:
                (dst / f.name).write_bytes(f.read_bytes())
            return reply(out="COUNTY_CHIPS 3\n")
        return reply()


@pytest.fixture
def fake(box, monkeypatch, tmp_path):
    remote = tmp_path / "remote"
    remote.mkdir()
    f = Fake(box, remote)
    f.now = 1000.0
    monkeypatch.setattr(box, "_sh", f)
    monkeypatch.setattr(box, "_now", lambda: f.now)                 # the driver's clock
    monkeypatch.setattr(box, "high_ports_reachable", lambda: True)  # no real network in tests
    monkeypatch.setattr(box, "ROOT", tmp_path / "project")          # so pull and teardown use temporary folders
    (tmp_path / "project").mkdir()
    return f


def rented(box, fake, now=1000.0, **offer_changes):
    fake.now = now
    return box.rent(good_offer(**offer_changes), sleep=NOSLEEP)


def put(root, rel, data):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode())
    return p


def ours(box, fake):
    return fake.instances[box.load_state()["instance_id"]]


# ---------------------------------------------------------------- offer filter (C1 to C4, C22)

def test_c1_paid_bandwidth_offers_are_rejected(box, offers):
    relaxed = dict(min_cores=0, min_ram_gb=0, min_disk=0, min_inet=0, min_reliability=0, min_cuda=0, n=50)
    picked = box.filter_offers(offers, **relaxed)
    assert picked, "the fixture should contain free-bandwidth RTX 5090 offers"
    assert all(o["inet_down_cost"] <= 0.001 and o["inet_up_cost"] <= 0.001 for o in picked)
    paid = [o for o in offers if o["gpu_name"] == "RTX 5090" and o["num_gpus"] == 1
            and o["verification"] == "verified" and o["inet_down_cost"] > 0.001]
    assert paid, "the fixture should contain a paid-bandwidth RTX 5090 offer"
    assert not {o["id"] for o in paid} & {o["id"] for o in picked}
    with pytest.raises(ValueError):
        box.filter_offers([good_offer(inet_up_cost=0.01)])
    with pytest.raises(ValueError):
        box.filter_offers([good_offer(inet_down_cost=0.01)])


def test_c2_offers_above_the_price_ceiling_are_rejected(box):
    assert box.filter_offers([good_offer(dph_total=1.30)])
    with pytest.raises(ValueError):
        box.filter_offers([good_offer(dph_total=1.31)])


@pytest.mark.parametrize("change", [
    {"cuda_max_good": 12.9}, {"disk_space": 99.0}, {"cpu_cores_effective": 15.0}, {"cpu_ram": 47 * 1024},
    {"inet_down": 799.0}, {"reliability2": 0.98}, {"rentable": False}, {"verification": "unverified"},
    {"verification": "deverified"},
])
def test_c3_each_unsuitable_property_is_rejected(box, change):
    assert box.filter_offers([good_offer()])
    with pytest.raises(ValueError, match="no offers matched"):
        box.filter_offers([good_offer(**change)])


def test_c4_one_per_machine_europe_first_then_price(box):
    pool = [good_offer(id=1, machine_id=7, dph_total=0.50, geolocation="Texas, US"),
            good_offer(id=2, machine_id=8, dph_total=0.90, geolocation="Denmark, DK"),
            good_offer(id=3, machine_id=8, dph_total=0.95, geolocation="Denmark, DK"),
            good_offer(id=4, machine_id=9, dph_total=0.70, geolocation="Czechia, CZ")]
    assert [o["id"] for o in box.filter_offers(pool)] == [4, 2, 1]
    assert [o["id"] for o in box.filter_offers(pool, n=1)] == [4]
    with pytest.raises(ValueError, match="no offers matched"):
        box.filter_offers([])


@pytest.mark.parametrize("change", [{"gpu_name": "RTX 3090"}, {"num_gpus": 2}, {"gpu_ram": 16000}])
def test_c22_an_offer_without_one_allowed_gpu_of_24gb_is_rejected(box, change, offers):
    with pytest.raises(ValueError):
        box.filter_offers([good_offer(**change)])
    assert all(o["gpu_name"] == "RTX 5090" and o["num_gpus"] == 1
               for o in box.filter_offers(offers, min_cores=0, min_ram_gb=0, min_disk=0, min_inet=0,
                                          min_reliability=0, min_cuda=0, n=50))


def test_c22b_the_4090_fallback_and_the_storage_priced_search(box, fake):
    fake.offers = [good_offer(id=9, gpu_name="RTX 4090", gpu_ram=24564)]
    assert [o["id"] for o in box.pick_offers()] == [9]
    searches = [c for c in fake.calls if c[1:3] == ["search", "offers"]]
    assert len(searches) == 2  # RTX 5090 first, then the fallback
    assert all(c[c.index("--storage") + 1] == "100" for c in searches)  # priced with the disk actually rented
    fake.offers = []
    with pytest.raises(ValueError):
        box.pick_offers()


def test_the_clis_output_is_read_whatever_comes_before_the_json(box, fake):
    listing = {"instances": [{"id": 7, "actual_status": "running"}], "instances_found": 1}
    assert box._last_json(raw(listing)) == listing                                     # several lines, as --raw prints
    assert box._last_json("Warning: your CLI is out of date\n" + raw(listing)) == listing
    assert box._last_json("note [1]\n" + raw([{"id": 3}])) == [{"id": 3}]
    with pytest.raises(ValueError):
        box._last_json("failed with error 502")
    fake.warning = "DEPRECATED: something will be removed\n"
    fake.offers = [good_offer(id=5)]
    assert [o["id"] for o in box.pick_offers()] == [5]
    assert box.instances() == []


# ---------------------------------------------------------------- money (C5, C6, C18, C21)

def test_c6_spend_and_deadline_arithmetic(box):
    r = box.new_rental(1, dph=1.0, storage=0.01, now=0.0, money_left=15.0)
    assert r["deadline_epoch"] == 8 * 3600  # the hour limit binds
    assert box.rental_cost(r, now=1800.0) == pytest.approx(0.5)
    box.switch_rate(r, 0.01, now=3600.0)  # stopped after one hour
    assert box.rental_cost(r, now=3600.0 + 7200.0) == pytest.approx(1.0 + 0.02)
    assert box.allowed_hours(2.0, 3.0) == pytest.approx(1.5)
    assert box.allowed_hours(1.0, -4.0) == 0.0


def test_c21_deadline_counts_from_rental_and_is_the_earlier_of_hours_and_money(box):
    r = box.new_rental(1, dph=1.0, storage=0.0, now=500.0, money_left=3.0)
    assert r["rented_at"] == 500.0 and r["deadline_epoch"] == 500.0 + 3 * 3600  # money runs out first
    r = box.new_rental(1, dph=0.5, storage=0.0, now=500.0, money_left=15.0)
    assert r["deadline_epoch"] == 500.0 + 8 * 3600  # hour limit first


def test_c5_renting_is_refused_when_the_money_left_does_not_cover_an_hour(box, fake):
    spent = box.new_rental(1, dph=1.0, storage=0.0, now=0.0, money_left=15.0)
    spent["intervals"][-1]["end"] = 14.5 * 3600  # $14.50 already gone
    spent["closed_reason"] = "done"
    box._save(box.HISTORY, [spent])
    with pytest.raises(box.BoxError, match="does not cover an hour"):
        rented(box, fake, now=60000.0, dph_total=0.9)
    assert not fake.instances and not fake.created()
    assert not box.budget_ok(2.0, 1.5) and box.budget_ok(1.0, 1.0)


def test_c18_spend_is_cumulative_across_boxes_and_stopped_time(box, fake):
    first = box.new_rental(1, dph=1.0, storage=0.1, now=0.0, money_left=15.0)
    box.switch_rate(first, 0.1, now=2 * 3600.0)       # ran 2 h = $2.00
    first["intervals"][-1]["end"] = 12 * 3600.0       # stopped 10 h at $0.10 = $1.00
    first["closed_reason"] = "restart failed"
    box._save(box.HISTORY, [first])
    now = 12 * 3600.0
    assert box.spent_total(now) == pytest.approx(3.0)
    assert box.cap_left(now) == pytest.approx(12.0)
    state = rented(box, fake, now=now, dph_total=2.0)
    # $12 left at $2/h, with the 10% price margin: 5.45 hours, not the 8-hour limit and not a full 6
    assert state["deadline_epoch"] == pytest.approx(now + 12.0 / (2.0 * box.PRICE_MARGIN) * 3600)
    assert state["deadline_epoch"] < now + 6 * 3600
    assert box.spent_total(now + 3600.0) == pytest.approx(5.0)


def test_c18b_a_slightly_higher_billed_price_is_booked_and_a_much_higher_one_is_refused(box, fake):
    fake.instance_dph = 0.95
    state = rented(box, fake, now=0.0, dph_total=0.90)
    assert state["dph"] == 0.95 and box.rental_cost(box.load_state(), 3600.0) == pytest.approx(0.95)
    box.abandon("test", sleep=NOSLEEP)
    fake.instance_dph = 1.20  # a third more than offered: the baked-in deadline no longer protects the cap
    with pytest.raises(box.BoxError, match="more than 110% of"):
        rented(box, fake, now=5000.0, dph_total=0.90)
    assert not fake.instances and box.load_state() is None


def test_c18c_state_lives_outside_the_repository():
    real = load_box()
    assert real.ROOT not in real.STATE.parents and real.ROOT not in real.HISTORY.parents
    assert real.STATE.parent == real.HISTORY.parent == real.STATE_DIR


# ---------------------------------------------------------------- renting and failure exits (C7, C8, C19, C24, C25)

def test_c7_the_instance_id_is_saved_before_setup_starts(box, fake):
    seen = []

    def spy(args):
        if fake.created() and args[:3] != ["vastai", "create", "instance"]:
            seen.append(box.STATE.exists() and box.load_state()["instance_id"])

    fake.on_call = spy
    state = rented(box, fake)
    assert seen and all(s == state["instance_id"] for s in seen)
    assert state["ssh_host"] == "ssh.example" and state["ssh_port"] == 2222


def test_c7b_the_watcher_is_installed_at_creation_and_confirmed_before_rent_returns(box, fake):
    state = rented(box, fake, now=5000.0, dph_total=1.0)
    inst = fake.instances[state["instance_id"]]
    assert inst["disk"] == "100"
    onstart = inst["onstart"]
    assert f"-lt {int(state['deadline_epoch'])} ]" in onstart  # the deadline is fixed before the box exists
    assert "cat > /root/watchdog.sh" in onstart and "setsid nohup sh /root/watchdog.sh" in onstart
    assert "echo $! > /root/watchdog.pid" in onstart
    assert state["deadline_epoch"] == 5000.0 + 8 * 3600
    assert box.load_state()["watchdog_armed"] is True  # rent itself checked the watcher over ssh
    assert any(c[0] == "ssh" and "echo ALIVE" in c[-1] for c in fake.calls)


def test_c7c_a_box_whose_watcher_cannot_be_confirmed_is_not_kept(box, fake):
    fake.watchdog = False
    with pytest.raises(box.BoxError, match="deadline watcher did not start"):
        rented(box, fake)
    assert not fake.instances and box.load_state() is None


def test_c19_a_box_that_never_runs_is_destroyed_and_its_cost_recorded(box, fake):
    fake.create_status = "loading"
    with pytest.raises(box.BoxError, match="never reached running"):
        rented(box, fake)
    assert not fake.instances and box.load_state() is None
    hist = box.load_history()
    assert len(hist) == 1 and hist[0]["closed_reason"] == "never reached running"
    assert hist[0]["intervals"][-1]["end"] is not None


def test_c19b_an_unreachable_box_is_destroyed(box, fake):
    fake.ssh_fail_times = 99
    with pytest.raises(box.BoxError, match="ssh failed"):
        rented(box, fake)
    assert not fake.instances and box.load_history()[0]["closed_reason"] == "ssh unreachable"


def test_c19c_a_third_replacement_is_refused(box, fake):
    fake.create_status = "loading"
    for _ in range(3):  # the first box and two replacements
        with pytest.raises(box.BoxError, match="never reached running"):
            rented(box, fake)
    fake.create_status = "running"
    with pytest.raises(box.BoxError, match="no further replacement"):
        rented(box, fake)
    assert len(fake.created()) == 3


def test_c19d_a_gpu_that_does_not_work_or_is_too_small_destroys_the_box(box, fake):
    rented(box, fake)
    fake.gpu_ok = False
    with pytest.raises(box.BoxError, match="GPU is not usable"):
        box.setup()
    assert not fake.instances and box.load_history()[-1]["closed_reason"] == "gpu check"
    fake.gpu_ok = True
    rented(box, fake, now=2000.0)
    fake.mem_error = "oom"
    with pytest.raises(box.BoxError, match="does not fit"):
        box.memcheck()
    assert not fake.instances and box.load_history()[-1]["closed_reason"] == "memory check"


def test_c19e_a_failed_install_or_a_check_that_could_not_run_keeps_the_box(box, fake):
    state = rented(box, fake)
    fake.install_ok = False
    with pytest.raises(box.BoxError, match="install failed") as e:
        box.setup()
    assert "pysheds" in str(e.value)  # the log tail, not a misleading GPU message
    assert state["instance_id"] in fake.instances and box.load_history() == []
    fake.install_ok = True
    assert box.setup() == "GPU NVIDIA GeForce RTX 5090"
    fake.mem_error = "import"  # the weights would not download: that says nothing about the GPU
    with pytest.raises(box.BoxError, match="could not run") as e:
        box.memcheck()
    assert "weights" in str(e.value) and state["instance_id"] in fake.instances and box.load_history() == []
    fake.mem_error = None
    assert box.memcheck() == "MEMCHECK_OK peak_gb=6.10"


def test_c19f_any_failure_after_the_box_exists_destroys_it(box, fake):
    fake.raise_on_poll = KeyboardInterrupt()  # the user interrupts while the box is booting
    with pytest.raises(KeyboardInterrupt):
        rented(box, fake)
    assert not fake.instances and box.load_state() is None and len(box.load_history()) == 1
    fake.raise_on_poll = subprocess.TimeoutExpired("vastai", 120)  # a hung API call is a BoxError, ridden out
    state = rented(box, fake, now=3000.0)
    assert state["instance_id"] in fake.instances


def test_c19g_a_dropped_status_poll_is_ridden_out(box, fake):
    fake.poll_errors = 2
    state = rented(box, fake)
    assert state["instance_id"] in fake.instances and box.load_history() == []


def test_c24_renting_is_refused_on_a_network_that_blocks_high_ports(box, fake, monkeypatch):
    monkeypatch.setattr(box, "high_ports_reachable", lambda: False)
    with pytest.raises(box.BoxError, match="blocks outgoing connections on high ports"):
        rented(box, fake)
    assert not fake.instances and box.load_state() is None and box.load_history() == []
    assert not fake.created()  # nothing rented, nothing charged


def test_c24b_a_refused_connection_counts_as_reachable_and_silence_does_not(box, monkeypatch):
    import socket

    def refuse(addr, timeout=None):
        raise ConnectionRefusedError

    def silent(addr, timeout=None):
        raise TimeoutError

    monkeypatch.setattr(socket, "create_connection", refuse)
    assert box.high_ports_reachable() is True   # the path is open, the port just has no listener
    monkeypatch.setattr(socket, "create_connection", silent)
    assert box.high_ports_reachable() is False  # dropped by a firewall


def test_c25_a_rented_box_is_labelled_and_only_its_own_id_is_ever_touched(box, fake):
    other = fake.add("cctv-potholes")  # another chat's box on the same account
    state = rented(box, fake)
    assert fake.instances[state["instance_id"]]["label"] == box.LABEL == "image-augmentation"
    box.stop(sleep=NOSLEEP)
    box.start(sleep=NOSLEEP)
    box.teardown(force_discard=True, sleep=NOSLEEP)
    assert list(fake.instances) == [other] and fake.instances[other]["actual_status"] == "running"
    touched = [c for c in fake.calls if c[0] == "vastai" and c[1] in ("destroy", "stop", "start")]
    assert touched and all(int(c[3]) == state["instance_id"] for c in touched)


def test_c25b_another_sessions_box_that_appears_while_renting_is_never_adopted(box, fake):
    fake.stranger_on_create = True
    fake.gone_offers = {11}  # our offer is gone (the CLI says so on stderr and exits 0) and a stranger's box appears
    state = box.rent_first([good_offer(id=11), good_offer(id=12)], sleep=NOSLEEP)
    assert fake.instances[state["instance_id"]]["label"] == box.LABEL
    assert [c[3] for c in fake.created()] == ["11", "12"]
    strangers = [i for i, inst in fake.instances.items() if inst["label"] == "cctv-potholes"]
    assert len(strangers) == 2 and state["instance_id"] not in strangers
    box.abandon("test", sleep=NOSLEEP)
    assert sorted(fake.instances) == sorted(strangers)  # ours is gone, theirs were never touched

    fake.gone_offers, fake.create_garbled = set(), True  # unreadable output, and a stranger with a newer id
    real_add = fake.add

    def add_ours_then_a_newer_stranger(label, status="running"):
        new = real_add(label, status)
        if label == box.LABEL:
            real_add("flood-depth")
        return new

    fake.stranger_on_create, fake.add = False, add_ours_then_a_newer_stranger
    state = box.rent_first([good_offer(id=13)], sleep=NOSLEEP)
    assert fake.instances[state["instance_id"]]["label"] == box.LABEL  # ours, not the newest on the account


def test_offers_that_vanish_are_skipped_and_only_one_box_is_rented(box, fake):
    fake.gone_offers = {11}
    state = box.rent_first([good_offer(id=11), good_offer(id=12), good_offer(id=13)], sleep=NOSLEEP)
    assert len(fake.instances) == 1 and state["instance_id"] in fake.instances
    assert [c[3] for c in fake.created()] == ["11", "12"]  # stopped after the first success
    box.abandon("test", sleep=NOSLEEP)
    fake.gone_offers = {21, 22}
    with pytest.raises(box.BoxError, match="none of the listed offers"):
        box.rent_first([good_offer(id=21), good_offer(id=22)], sleep=NOSLEEP)
    assert not fake.instances
    with pytest.raises(box.BoxError, match="none of the listed offers"):
        box.rent_first([good_offer(id=30)], only=99, sleep=NOSLEEP)


def test_noisy_or_unreadable_create_output_never_rents_a_second_box(box, fake):
    fake.warning = "Warning: your CLI is out of date\n"
    state = box.rent_first([good_offer(id=1), good_offer(id=2)], sleep=NOSLEEP)
    assert len(fake.created()) == 1 and box.load_state()["instance_id"] == state["instance_id"]
    box.abandon("test", sleep=NOSLEEP)
    fake.warning, fake.create_garbled = "", True  # no JSON at all, but our labelled instance did appear
    state = box.rent_first([good_offer(id=3), good_offer(id=4)], sleep=NOSLEEP)
    assert len(fake.created()) == 2 and list(fake.instances) == [state["instance_id"]]  # found, not rented again
    box.abandon("test", sleep=NOSLEEP)
    fake.listing_lag = 2  # and the listing takes two polls to show it
    state = box.rent_first([good_offer(id=5), good_offer(id=6)], sleep=NOSLEEP)
    assert len(fake.created()) == 3 and list(fake.instances) == [state["instance_id"]]


def test_c8_teardown_raises_if_the_instance_is_still_listed(box, fake):
    rented(box, fake)
    fake.destroy_works = False
    with pytest.raises(box.BoxError, match="still listed"):
        box.teardown(force_discard=True, sleep=NOSLEEP)
    assert box.load_state() is not None  # not booked as gone


def test_c8b_an_instance_that_is_already_gone_counts_as_destroyed(box, fake):
    state = rented(box, fake)
    fake.instances.clear()  # the host removed it
    box.teardown(force_discard=True, now=4600.0, sleep=NOSLEEP)
    assert box.load_state() is None and box.load_history()[-1]["closed_reason"] == "done"
    assert box.spent_total(10 * 3600.0) == pytest.approx(state["dph"])  # one hour booked, and it stops growing
    rented(box, fake, now=5000.0)
    fake.destroy_errors = 1  # one API error (the CLI still exits 0), then it works
    box.abandon("test", sleep=NOSLEEP)
    assert not fake.instances


# ---------------------------------------------------------------- the teardown gate and pull (C9, C10)

def finished_job(box, fake, name="grid"):
    job = box.run(name, "true", sleep=NOSLEEP)
    fake.rc[job] = 0
    return job


def test_c9_teardown_refuses_until_the_results_on_the_box_are_on_this_machine(box, fake):
    state = rented(box, fake)
    job = box.run("grid", "true", sleep=NOSLEEP)
    put(fake.remote, "data/processed/vision/frozen/metrics.json", '{"a": 1}')
    put(fake.remote, "data/processed/vision/frozen/emb.npy", b"\x00" * 64)
    box.pull("data/processed/vision", box.ROOT / "data/processed/vision")
    with pytest.raises(box.BoxError, match="still running"):  # a pull while the job runs does not open the gate
        box.teardown(sleep=NOSLEEP)
    fake.rc[job] = 0
    put(fake.remote, "data/processed/vision/finetune/report.md", "written after the pull")
    with pytest.raises(box.BoxError, match="1 result files on the box are not on this machine"):
        box.teardown(sleep=NOSLEEP)
    assert state["instance_id"] in fake.instances
    box.pull("data/processed/vision", box.ROOT / "data/processed/vision")
    put(box.ROOT, "data/processed/vision/frozen/metrics.json", '{"a": 2}')  # altered locally after the pull
    with pytest.raises(box.BoxError, match="differ"):
        box.teardown(sleep=NOSLEEP)
    box.pull("data/processed/vision", box.ROOT / "data/processed/vision")
    put(box.ROOT, "data/processed/vision/extra_local_note.txt", "extra local files are fine")
    box.teardown(now=3000.0, sleep=NOSLEEP)
    assert not fake.instances and box.load_state() is None
    assert box.load_history()[-1]["closed_reason"] == "done" and box.abandoned_count() == 0


def test_c9b_an_empty_results_folder_needs_force(box, fake):
    rented(box, fake)
    finished_job(box, fake, "fetch")
    with pytest.raises(box.BoxError, match="holds no results"):
        box.teardown(sleep=NOSLEEP)
    assert fake.instances
    box.teardown(force_discard=True, now=3000.0, sleep=NOSLEEP)
    assert not fake.instances


def test_c9c_a_job_killed_at_the_deadline_does_not_block_teardown_but_its_files_are_still_checked(box, fake):
    rented(box, fake)
    job = box.run("grid", "true", sleep=NOSLEEP)
    fake.dead.add(job)  # the watcher killed it: no exit status, no process
    assert box.job_state("grid") == "died" and box.running_jobs() == []
    with pytest.raises(box.BoxError, match="died without an exit status"):
        box.wait("grid", sleep=NOSLEEP)
    put(fake.remote, "data/processed/vision/finetune/none/seed0/fold0.parquet", b"partial results")
    with pytest.raises(box.BoxError, match="not on this machine"):
        box.teardown(sleep=NOSLEEP)
    box.pull("data/processed/vision", box.ROOT / "data/processed/vision")
    box.teardown(now=3000.0, sleep=NOSLEEP)
    assert not fake.instances


def test_c9d_a_stopped_box_past_its_deadline_can_be_brought_up_briefly_to_copy_results(box, fake):
    state = rented(box, fake, now=0.0, dph_total=1.0)
    finished_job(box, fake, "grid")
    put(fake.remote, "data/processed/vision/frozen/metrics.json", '{"a": 1}')
    ours(box, fake)["actual_status"] = "exited"  # the watcher stopped it at the deadline
    fake.now = state["deadline_epoch"] + 600
    with pytest.raises(box.BoxError, match="not running"):  # the gate cannot check a box it cannot reach
        box.teardown(sleep=NOSLEEP)
    with pytest.raises(box.BoxError, match="past its deadline"):
        box.start(sleep=NOSLEEP)
    with pytest.raises(box.BoxError, match="past its deadline"):
        box.run("more", "true", sleep=NOSLEEP)
    box.start(sleep=NOSLEEP, grace=True)
    assert ours(box, fake)["actual_status"] == "running" and box.load_state()["deadline_epoch"] == state["deadline_epoch"]
    with pytest.raises(box.BoxError, match="past its deadline"):  # grace is for copying, not for new work
        box.run("more", "true", sleep=NOSLEEP)
    box.pull("data/processed/vision", box.ROOT / "data/processed/vision")
    box.teardown(sleep=NOSLEEP)
    assert not fake.instances
    script = box.watchdog_script(state["deadline_epoch"])
    assert f"-ge {int(state['deadline_epoch'])} ]; then sleep {box.GRACE_MIN * 60}; fi" in script  # the grace window


def test_c9e_grace_is_refused_when_the_money_left_does_not_cover_it(box, fake):
    state = rented(box, fake, now=0.0, dph_total=1.0)
    box.stop(now=3600.0, sleep=NOSLEEP)
    spent = box.new_rental(2, dph=1.0, storage=0.0, now=0.0, money_left=15.0)
    spent["intervals"][-1]["end"] = 13.9 * 3600
    spent["closed_reason"] = "done"
    box._save(box.HISTORY, [spent])
    fake.now = state["deadline_epoch"] + 60
    with pytest.raises(box.BoxError, match="does not cover 20 more minutes"):
        box.start(sleep=NOSLEEP, grace=True)
    assert ours(box, fake)["actual_status"] == "exited"


def test_c10_pull_copies_checks_and_guards_its_destination(box, fake):
    rented(box, fake)
    put(fake.remote, "data/processed/vision/frozen/metrics.json", '{"a": 1}')
    put(fake.remote, "data/processed/vision/ndvi_stats.parquet", b"PAR1" + b"\x01" * 100)
    dest = box.ROOT / "data/processed/vision"
    put(box.ROOT, "data/processed/vision/frozen/metrics.json", "older result")
    assert box.pull("data/processed/vision", dest, now=1234.0) == 2
    assert (dest / "frozen/metrics.json").read_text() == '{"a": 1}'  # results replace older results
    assert (dest / "ndvi_stats.parquet").read_bytes().startswith(b"PAR1")
    assert not list(dest.glob(".incoming-*")) and box.load_state()["last_verified_pull_at"] == 1234.0
    for bad in (box.ROOT / "data/processed", box.ROOT / "data/raw", box.ROOT, box.ROOT / "src"):
        with pytest.raises(box.BoxError, match="pull may only write into"):
            box.pull("data/processed/vision", bad)  # e.g. it must never replace segments_targets.parquet
    for bad in ("../etc", "/etc", "data/$(touch x)", "data/a b", ".", "data", "src", "src/model", ""):
        with pytest.raises(box.BoxError, match="plain path"):
            box.pull(bad, dest)


def test_c10b_a_pull_that_does_not_match_the_boxes_list_is_refused(box, fake):
    rented(box, fake)
    put(fake.remote, "data/processed/vision/frozen/metrics.json", '{"a": 1}')
    put(box.ROOT, "data/processed/vision/frozen/metrics.json", "older result")
    fake.corrupt_pull = True
    with pytest.raises(box.BoxError, match="do not match the box's list"):
        box.pull("data/processed/vision", box.ROOT / "data/processed/vision")
    assert (box.ROOT / "data/processed/vision/frozen/metrics.json").read_text() == "older result"  # untouched
    assert box.load_state()["last_verified_pull_at"] == 0.0


def test_c10c_pulling_chips_never_replaces_one_that_is_already_here(box, fake):
    rented(box, fake)
    for name in ("a.npy", "b.npy", "c.npy"):
        put(fake.remote, f"data/chips/{name}", b"from the box " + name.encode())
    put(box.ROOT, "data/chips/a.npy", "already here")
    assert box.county_chips() == 2  # the county copy goes through the same guard
    assert (box.ROOT / "data/chips/a.npy").read_text() == "already here"
    assert (box.ROOT / "data/chips/b.npy").read_bytes() == b"from the box b.npy"
    assert box.pull("data/chips", box.ROOT / "data/chips", no_overwrite=False) == 0  # the flag cannot be turned off


def test_c10d_verify_manifest_detects_every_kind_of_difference(box, tmp_path):
    d = tmp_path / "got"
    put(d, "a.json", "alpha")
    put(d, "sub/b.npy", b"\x00\x01\x02")
    good = [["a.json", 5, box.file_sha256(d / "a.json")], ["sub/b.npy", 3, box.file_sha256(d / "sub" / "b.npy")]]
    assert box.verify_manifest(good, d) == [] and box.missing_or_different(good, d) == []
    assert box.verify_manifest(good + [["missing.txt", 1, "0" * 64]], d) == ["missing.txt"]
    assert box.verify_manifest(good[:1], d) == ["sub/b.npy"]            # an extra local file
    assert box.missing_or_different(good[:1], d) == []                   # which the teardown gate allows
    assert box.verify_manifest([["a.json", 6, good[0][2]], good[1]], d) == ["a.json"]  # size
    assert box.verify_manifest([["a.json", 5, "f" * 64], good[1]], d) == ["a.json"]    # hash


# ---------------------------------------------------------------- self-stop and watchdog (C20, C23)

def test_c23_a_box_without_its_own_key_is_abandoned(box, fake):
    rented(box, fake)
    fake.has_key = False
    with pytest.raises(box.SelfStopUnavailable):
        box.selfstop_test(sleep=NOSLEEP)
    assert not fake.instances and box.load_history()[-1]["closed_reason"] == "no self-stop"


def test_c23b_a_box_that_does_not_stop_itself_is_abandoned(box, fake):
    rented(box, fake)
    fake.selfstop_works = False
    with pytest.raises(box.SelfStopUnavailable):
        box.selfstop_test(sleep=NOSLEEP)
    assert not fake.instances and box.load_history()[-1]["closed_reason"] == "no self-stop"


def test_c23c_a_working_self_stop_restarts_and_confirms_the_watcher(box, fake):
    rented(box, fake)
    state = box.selfstop_test(sleep=NOSLEEP)
    assert fake.instances[state["instance_id"]]["actual_status"] == "running"
    assert box.load_state()["watchdog_armed"] is True
    rates = [iv["rate"] for iv in box.load_state()["intervals"]]
    assert rates == [state["dph"], state["storage_rate"], state["dph"]]  # running, stopped, running


def test_c23d_a_failed_restart_is_abandoned(box, fake):
    rented(box, fake)
    fake.start_works = False
    with pytest.raises(box.BoxError, match="did not restart"):
        box.selfstop_test(sleep=NOSLEEP)
    assert not fake.instances and box.load_history()[-1]["closed_reason"] == "restart failed"


def test_c23e_the_watcher_waits_for_the_fixed_deadline_then_keeps_stopping_the_box(box):
    script = box.watchdog_script(1234567.9)
    lines = script.splitlines()
    assert "CONTAINER_API_KEY" in lines[0]  # it reads the box's own id and key
    assert "while [ $(date +%s) -lt 1234567 ]; do sleep 30; done" in lines
    stop = "while true; do vastai stop instance $CONTAINER_ID --api-key $CONTAINER_API_KEY; sleep 60; done"
    assert lines[-1] == stop  # repeated for as long as the box is up: the CLI's exit status cannot be trusted
    assert "until vastai stop" not in script
    kill = next(i for i, ln in enumerate(lines) if "kill ${p#/proc/}" in ln)
    assert kill < lines.index("touch /root/DEADLINE_HIT") < len(lines) - 1  # jobs first, then the stop loop
    assert "pkill" not in script and "pgrep" not in script  # nothing the image might lack
    for text in (script, box.onstart_script(1234567.9)):
        assert subprocess.run(["sh", "-n"], input=text, text=True, capture_output=True).returncode == 0  # valid shell


@pytest.mark.parametrize("restart", ["selfstop", "start"])
def test_c23f_a_box_whose_watcher_cannot_be_started_is_stopped_not_left_running(box, fake, restart):
    state = rented(box, fake)
    if restart == "start":
        box.stop(sleep=NOSLEEP)
    fake.watchdog = False  # after the restart the watcher is not running and cannot be started
    with pytest.raises(box.BoxError, match="so the box was stopped"):
        box.selfstop_test(sleep=NOSLEEP) if restart == "selfstop" else box.start(sleep=NOSLEEP)
    assert fake.instances[state["instance_id"]]["actual_status"] == "exited"
    s = box.load_state()
    assert s["watchdog_armed"] is False and s["intervals"][-1]["rate"] == s["storage_rate"]


def test_c23h_a_stop_that_the_api_quietly_refuses_is_not_taken_for_a_stop(box, fake):
    state = rented(box, fake)
    box.stop(sleep=NOSLEEP)
    fake.watchdog, fake.quiet_stop_failure = False, True  # cannot arm, and `vastai stop` exits 0 without stopping
    with pytest.raises(box.BoxError, match="did not stop, so it was destroyed"):
        box.start(sleep=NOSLEEP)
    assert state["instance_id"] not in fake.instances  # not left running, unwatched, booked as "stopped"
    assert box.load_state() is None and box.load_history()[-1]["closed_reason"] == "unwatched and would not stop"
    fake.watchdog = True
    rented(box, fake, now=9000.0)
    with pytest.raises(box.BoxError, match="did not stop"):  # an explicit stop is confirmed by status too
        box.stop(sleep=NOSLEEP)
    assert box.load_state()["intervals"][-1]["rate"] == box.load_state()["dph"]  # still billed as running


def test_c23g_the_watcher_is_started_over_ssh_when_the_start_up_script_did_not(box, fake):
    rented(box, fake)
    answers = iter([False, True])  # not running, then running after the launch
    real_ssh = fake.ssh

    def ssh(cmd, input, stdin, stdout):
        if "echo ALIVE" in cmd:
            return reply(out="ALIVE\n") if next(answers) else reply(rc=1)
        return real_ssh(cmd, input, stdin, stdout)

    fake.ssh = ssh
    box.arm_watchdog()
    sent = [c[-1] for c in fake.calls if c[0] == "ssh"]
    assert "cat > /root/watchdog.sh" in sent and box.WATCHDOG_LAUNCH in sent
    assert box.load_state()["watchdog_armed"] is True


def test_c20_launching_a_job_is_refused_without_the_deadline_watcher(box, fake):
    rented(box, fake)
    fake.watchdog = False
    with pytest.raises(box.BoxError, match="deadline watcher"):
        box.run("fetch", "true", sleep=NOSLEEP)
    assert box.load_state()["jobs"] == {}
    liveness = [c[-1] for c in fake.calls if c[0] == "ssh" and "echo ALIVE" in c[-1]]
    # alive means the recorded pid exists AND is the watcher: a stale pid file or a reused pid does not count
    assert liveness and all("/root/watchdog.pid" in c and "grep -qa watchdog.sh /proc/$p/cmdline" in c for c in liveness)


def test_stop_and_start_switch_the_billing_rate_and_never_extend_the_deadline(box, fake):
    state = rented(box, fake, now=0.0)
    box.stop(now=3600.0, sleep=NOSLEEP)
    assert box.load_state()["watchdog_armed"] is False
    box.start(now=7200.0, sleep=NOSLEEP)
    s = box.load_state()
    assert s["watchdog_armed"] is True and s["deadline_epoch"] == state["deadline_epoch"]
    assert box.rental_cost(s, 7200.0) == pytest.approx(state["dph"] + state["storage_rate"])


# ---------------------------------------------------------------- jobs (C16, C17)

def test_c16_a_rerun_gets_a_new_id_and_never_reads_the_old_exit_status(box, fake):
    rented(box, fake)
    first = box.run("fetch", "true", now=2000.0, sleep=NOSLEEP)
    fake.rc[first] = 0
    assert box.job_status("fetch")[0] == 0 and box.job_state("fetch") == "finished"
    second = box.run("fetch", "true", now=2060.0, sleep=NOSLEEP)
    assert second != first and box.load_state()["jobs"]["fetch"] == second
    assert box.job_status("fetch")[0] is None  # the earlier run's exit status is not reported
    assert box.running_jobs() == ["fetch"] and box.job_state("fetch") == "running"
    fake.rc[second] = 3
    assert box.wait("fetch", sleep=NOSLEEP) == 3 and box.running_jobs() == []
    launch = [c[-1] for c in fake.calls if c[0] == "ssh" and "setsid nohup" in c[-1] and second in c[-1]]
    assert len(launch) == 1  # launched exactly once
    assert f"{second}.rc.tmp" in launch[0] and f"mv logs/{second}.rc.tmp logs/{second}.rc" in launch[0]
    assert "mkdir -p logs" in launch[0]


def test_c16b_a_dropped_connection_never_launches_a_job_twice(box, fake):
    rented(box, fake)
    real_ssh = fake.ssh
    fails = iter([True])

    def ssh(cmd, input, stdin, stdout):
        if "setsid nohup sh -c" in cmd and next(fails, False):
            return reply(rc=255, err="Connection reset")
        return real_ssh(cmd, input, stdin, stdout)

    fake.ssh = ssh
    with pytest.raises(box.BoxError, match="ssh failed 1 times"):
        box.run("grid", "true", sleep=NOSLEEP)
    assert sum("setsid nohup sh -c" in c[-1] for c in fake.calls if c[0] == "ssh") == 1


def test_c17_a_job_that_fails_to_launch_raises(box, fake):
    rented(box, fake)
    fake.launch_ok = False
    with pytest.raises(box.BoxError, match="did not start"):
        box.run("fetch", "true", sleep=NOSLEEP)
    assert "fetch" not in box.load_state()["jobs"]


@pytest.mark.parametrize("name", ["$(touch pwned)", "a b", "x;y", "", "../x", "a'b"])
def test_c17b_a_job_name_that_is_not_a_plain_word_is_refused(box, fake, name):
    rented(box, fake)
    n_ssh = sum(c[0] == "ssh" for c in fake.calls)
    with pytest.raises(box.BoxError, match="job name"):
        box.run(name, "true", sleep=NOSLEEP)
    assert sum(c[0] == "ssh" for c in fake.calls) == n_ssh  # nothing reached the box


def test_c17c_a_command_with_quotes_reaches_the_box_intact(box, fake):
    rented(box, fake)
    job = box.run("grid", """python -c 'print("a b")' && echo "$HOME" """, sleep=NOSLEEP)
    launch = [c[-1] for c in fake.calls if c[0] == "ssh" and job in c[-1] and "setsid" in c[-1]][0]
    inner = launch.split("sh -c ", 1)[1].split(f" > logs/{job}.log")[0]
    assert shlex.split(inner)[0].startswith("""python -c 'print("a b")' && echo "$HOME" """)


def test_wait_times_out_on_a_job_that_never_finishes(box, fake):
    rented(box, fake)
    box.run("grid", "true", sleep=NOSLEEP)
    with pytest.raises(box.BoxError, match="still running"):
        box.wait("grid", poll_s=30, timeout_s=90, sleep=NOSLEEP)


# ---------------------------------------------------------------- ssh (C13)

def test_c13_ssh_succeeds_after_two_failures_and_raises_after_five(box, fake):
    rented(box, fake)
    fake.calls.clear()
    fake.ssh_fail_times = 2
    assert box.ssh("true", sleep=NOSLEEP).returncode == 0
    assert len(fake.calls) == 3
    fake.ssh_fail_times = 5
    with pytest.raises(box.BoxError, match="ssh failed 5 times"):
        box.ssh("true", sleep=NOSLEEP)


def test_c13b_a_failing_remote_command_is_not_retried_and_a_hang_is_a_box_error(box, fake, monkeypatch):
    rented(box, fake)
    monkeypatch.setattr(fake, "ssh", lambda cmd, i, si, so: reply(rc=2, err="boom"))
    fake.calls.clear()
    with pytest.raises(box.BoxError, match="remote command failed"):
        box.ssh("false", sleep=NOSLEEP)
    assert len(fake.calls) == 1

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("ssh", 600)

    monkeypatch.setattr(box, "_sh", hang)
    with pytest.raises(box.BoxError, match="timed out"):
        box.ssh("sleep 9999", sleep=NOSLEEP)
    with pytest.raises(box.BoxError, match="timed out"):
        box.vast("show", "instances-v1", "--raw")


# ---------------------------------------------------------------- shipping (C11, C12)

def make_project(root):
    for rel, text in {"src/a.py": "x = 1\n", "src/model/b.py": "y = 2\n", "tests/vision/test_x.py": "z = 3\n",
                      "scripts/cloud/box.py": "w = 4\n", "pyproject.toml": "[project]\n", "uv.lock": "lock\n",
                      ".python-version": "3.11\n", "data/raw/ncdot_joined.parquet": "p",
                      "data/raw/naip_2022_index.parquet": "q", "src/__pycache__/a.cpython-311.pyc": "junk",
                      "src/a 2.py": "icloud duplicate\n", "data/raw/other.parquet": "not listed"}.items():
        put(root, rel, text)


EXPECTED_BUNDLE = sorted([".python-version", "data/raw/naip_2022_index.parquet", "data/raw/ncdot_joined.parquet",
                          "pyproject.toml", "scripts/cloud/box.py", "src/a.py", "src/model/b.py",
                          "tests/vision/test_x.py", "uv.lock"])


def test_c12_the_push_list_holds_only_the_expected_paths(box, tmp_path):
    make_project(tmp_path)
    assert box.bundle_files(tmp_path) == EXPECTED_BUNDLE
    assert all(not e.startswith(("/", "~", "..")) and ".git" not in e and ".config" not in e for e in box.PUSH_LIST)
    put(tmp_path, "data/processed/segments_targets.parquet", "t")
    assert "data/processed/segments_targets.parquet" in box.bundle_files(tmp_path)
    (tmp_path / "uv.lock").unlink()
    with pytest.raises(box.BoxError, match="missing uv.lock"):
        box.bundle_files(tmp_path)


def test_c12b_push_sends_exactly_the_bundle_and_records_the_code_hash(box, fake):
    rented(box, fake)
    make_project(box.ROOT)
    digest = box.push()
    sent = sorted(p.relative_to(fake.remote).as_posix() for p in fake.remote.rglob("*") if p.is_file())
    assert sent == sorted(EXPECTED_BUNDLE + ["CODE_HASH"])
    assert (fake.remote / "CODE_HASH").read_text().strip() == digest == box.code_hash(box.ROOT)
    assert (fake.remote / "src/model/b.py").read_text() == "y = 2\n"
    assert not (box.LOGS / "cloud_push.tar").exists()
    put(box.ROOT, "src/settings.py", "API" + "_KEY = 'A1b2C3d4E5f6G7h8I9j0K1l2'\n")
    before = sum(c[0] == "ssh" for c in fake.calls)
    with pytest.raises(box.BoxError, match="look like they hold a key"):
        box.push()
    assert sum(c[0] == "ssh" for c in fake.calls) == before  # refused before anything was sent


@pytest.mark.parametrize("rel,text", [
    ("src/vast_api_key", "abc"),
    ("src/deploy.pem", "abc"),
    ("src/server.key", "abc"),
    ("src/id_ed25519", "abc"),
    ("src/.env", "A=1"),
    ("src/.env.local", "A=1"),
    ("src/aws_credentials.json", "{}"),
    ("src/creds.txt", "secret_access" + "_key=abcdefghijklmnop"),
    ("src/creds2.txt", "AWS_SECRET_ACCESS" + "_KEY=abcdefghijklmnop"),
    ("src/k.py", "-----BEGIN OPENSSH PRIVATE" + " KEY-----"),
    ("src/cfg.toml", "api" + "_key = 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4'"),
    ("src/upper.py", "VAST_API" + "_KEY = \"0123456789abcdef0123456789abcdef\""),
    ("src/camel.json", '{"api' + 'Key": "0123456789abcdef0123456789"}'),
    ("src/gh.py", "t = 'gh" + "p_" + "a" * 36 + "'"),
    ("src/pw.py", "PASS" + "WORD = 'correct-horse-battery'"),
    ("src/notes.csv", "name,value\ntok" + "en=abcdefghijklmnopqrstuvwx\n"),
    ("src/aws.py", "k = 'AKIA" + "ABCDEFGHIJKLMNOP'"),
])
def test_c11_a_bundle_that_looks_like_it_holds_a_key_is_refused(box, tmp_path, rel, text):
    make_project(tmp_path)
    box.scan_for_keys(box.bundle_files(tmp_path), tmp_path)  # the clean project passes
    put(tmp_path, rel, text)
    files = sorted(set(box.bundle_files(tmp_path)) | {rel})
    with pytest.raises(box.BoxError, match="look like they hold a key"):
        box.scan_for_keys(files, tmp_path)


def test_c11c_ordinary_code_that_mentions_tokens_or_keys_is_not_refused(box, tmp_path):
    make_project(tmp_path)
    put(tmp_path, "src/ordinary.py",
        "tok" + "en = get_token(settings)\n"
        "api" + "_key = os.environ['VAST_API" + "_KEY']\n"
        "pass" + "word = prompt_for_password()\n"
        "secret" + " = load_secret(path, mode='r')\n"
        "tok" + "ens = tokenizer.tokenize(text_of_the_document)\n")
    box.scan_for_keys(box.bundle_files(tmp_path), tmp_path)


def test_c11b_the_real_bundle_holds_no_key():
    real = load_box()
    files = [f for f in real.bundle_files(real.ROOT) if not f.endswith(".parquet")]
    assert len(files) > 20
    real.scan_for_keys(files, real.ROOT)


def test_code_hash_is_stable_and_changes_with_a_file(box, tmp_path):
    make_project(tmp_path)
    h = box.code_hash(tmp_path)
    assert h == box.code_hash(tmp_path) and len(h) == 64
    put(tmp_path, "src/a 2.py", "changed duplicate\n")
    assert box.code_hash(tmp_path) == h  # iCloud duplicates are not part of the code
    put(tmp_path, "src/model/b.py", "y = 3\n")
    assert box.code_hash(tmp_path) != h
    h2 = box.code_hash(tmp_path)
    put(tmp_path, "uv.lock", "other lock\n")
    assert box.code_hash(tmp_path) != h2


# ---------------------------------------------------------------- photo checks (C14, C15)

BANNER = "112,393 chips to cut from 4,012 NAIP tiles with 64 workers (37 midpoints outside NAIP 2022 coverage)\n"
FINAL = "[chips] 112,393/112,393 (100.0%)  80.0 chips/s  12 failed  done in 1404.9s\n"
RETRY = ("49 chips to cut from 40 NAIP tiles with 64 workers (37 midpoints outside NAIP 2022 coverage)\n"
         "[chips] 12/12 (100.0%)  3.0 chips/s  2 failed  done in 4.0s\n")


def test_c14_log_parsing_and_the_success_only_rate(box):
    p = box.parse_chips_log(BANNER + "[chips] 500/112,393 (0.4%)  70.1 chips/s  0 failed  eta 26.6 min\n" + FINAL)
    assert p == {"to_cut": 112393, "uncovered": 37, "done": 112393, "failed": 12, "seconds": 1404.9}
    trial = box.parse_chips_log("500 chips to cut from 380 NAIP tiles with 32 workers\n"
                                "[chips] 500/500 (100.0%)  50.0 chips/s  100 failed  done in 10.0s\n")
    assert trial["uncovered"] == 0
    assert box.ok_rate(trial) == pytest.approx(40.0)  # 400 successes in 10 s, not 50
    nothing = box.parse_chips_log("0 chips to cut from 0 NAIP tiles with 64 workers (37 midpoints outside NAIP 2022 coverage)\n")
    assert nothing == {"to_cut": 0, "uncovered": 37, "done": 0, "failed": 0, "seconds": 0.0}
    with pytest.raises(box.BoxError, match="did not finish"):
        box.parse_chips_log(BANNER)
    with pytest.raises(box.BoxError, match="no chips banner"):
        box.parse_chips_log("Traceback (most recent call last):\n")


def test_c14c_a_log_with_several_runs_is_read_from_its_last_run(box):
    both = box.parse_chips_log(BANNER + FINAL + RETRY)
    assert both == {"to_cut": 49, "uncovered": 37, "done": 12, "failed": 2, "seconds": 4.0}  # the retry, not a mix
    killed = BANNER + FINAL + "37 chips to cut from 30 NAIP tiles with 64 workers\n[chips] 5/37 (13.5%)  2.0 chips/s  0 failed  eta 0.3 min\n"
    with pytest.raises(box.BoxError, match="did not finish"):  # a finished run followed by a killed one
        box.parse_chips_log(killed)


def test_c14b_the_census_must_add_up_and_failures_stay_under_half_a_percent(box):
    parsed = {"to_cut": 49, "uncovered": 37, "done": 49, "failed": 12, "seconds": 5.0}
    assert box.census(112443 - 49, parsed)["on_disk"] == 112394
    with pytest.raises(box.BoxError, match="does not add up"):
        box.census(112443 - 50, parsed)
    many = dict(parsed, failed=563)  # 0.5007% of 112,443
    with pytest.raises(box.BoxError, match="above 0.5%"):
        box.census(112443 - 563 - 37, many)
    box.census(112443 - 562 - 37, dict(parsed, failed=562))  # 0.4998% passes


def test_c14d_a_failed_fetch_contract_stops_the_box_and_asking_too_early_does_not(box, fake, monkeypatch):
    state = rented(box, fake)
    monkeypatch.setattr(box, "TOTAL_SEGMENTS", 10)
    with pytest.raises(box.BoxError, match="no job named fetch"):  # never launched: an error, nothing more
        box.fetch_census(sleep=NOSLEEP)
    job = box.run("fetch", "true", sleep=NOSLEEP)
    with pytest.raises(box.BoxError, match="still running; the box is untouched"):
        box.fetch_census(sleep=NOSLEEP)
    assert ours(box, fake)["actual_status"] == "running"  # asking early must not stop the box and kill the fetch
    fake.rc[job] = 0
    fake.logs[job] = ("10 chips to cut from 9 NAIP tiles with 64 workers (1 midpoints outside NAIP 2022 coverage)\n"
                      "[chips] 9/9 (100.0%)  30.0 chips/s  0 failed  done in 0.3s\n")
    for i in range(9):
        put(fake.remote, f"data/chips/c{i}.npy", b"x")
    got = box.fetch_census()
    assert {k: got[k] for k in ("on_disk", "failed", "uncovered", "total")} == {"on_disk": 9, "failed": 0,
                                                                                "uncovered": 1, "total": 10}
    assert got["rate"] == pytest.approx(30.0)
    (fake.remote / "data/chips/c0.npy").unlink()  # a photo is missing: 8 + 0 + 1 is not 10
    with pytest.raises(box.BoxError, match="does not add up"):
        box.fetch_census(sleep=NOSLEEP)
    assert fake.instances[state["instance_id"]]["actual_status"] == "exited"  # stopped, not destroyed
    assert box.load_state() is not None


def test_c15_a_differing_photo_hash_is_detected(box):
    mac = box.parse_digests("a.npy 111\nb.npy 222\nc.npy 333\nnoise line here\n")
    assert mac == {"a.npy": "111", "b.npy": "222", "c.npy": "333"}
    assert box.compare_digests(mac, dict(mac)) == []
    assert box.compare_digests(mac, {**mac, "b.npy": "999"}) == ["b.npy"]
    assert box.compare_digests(mac, {"a.npy": "111", "b.npy": "222"}) == ["c.npy"]  # missing on the box
    extra = dict(mac, **{"d.npy": "444"})
    assert box.compare_digests(mac, extra, names=mac) == []  # only the Mac's photos are compared
    assert box.compare_digests(mac, extra) == ["d.npy"]


def photos(n=4, seed=0):
    rng = np.random.default_rng(seed)
    return {f"ncdot_{i}_0.000.npy": rng.integers(0, 255, size=(4, 8, 8), dtype=np.uint8) for i in range(n)}


def mac_photos(tmp_path, mine):
    local = tmp_path / "mac_chips"
    local.mkdir()
    for name, arr in mine.items():
        np.save(local / name, arr)
    return local


def test_c15b_the_identity_check_passes_on_equal_pixels_and_destroys_the_box_on_a_difference(box, fake, tmp_path,
                                                                                            monkeypatch):
    monkeypatch.setattr(box, "IDENTITY_MIN", 4)
    mine = photos()
    local = mac_photos(tmp_path, mine)
    assert box.local_digests(local) == {n: hashlib.sha256(a.tobytes()).hexdigest() for n, a in mine.items()}
    rented(box, fake)
    fake.box_chips = {**mine, "extra_on_box.npy": np.zeros((4, 8, 8), dtype=np.uint8)}
    assert box.identity_check(local, sleep=NOSLEEP) == 4 and fake.instances  # extras on the box are fine
    changed = dict(mine)
    name = sorted(changed)[1]
    changed[name] = changed[name].copy()
    changed[name][0, 0, 0] ^= 1  # one pixel differs in one photo
    fake.box_chips = changed
    with pytest.raises(box.BoxError, match="1 of 4 photos differ"):
        box.identity_check(local, sleep=NOSLEEP)
    assert not fake.instances and box.load_history()[-1]["closed_reason"] == "photo identity"
    rented(box, fake, now=2000.0)
    with pytest.raises(box.BoxError, match="no photos on this machine"):
        box.identity_check(tmp_path / "empty", sleep=NOSLEEP)


def test_c15d_a_photo_that_failed_to_download_is_retried_and_never_condemns_the_box(box, fake, tmp_path, monkeypatch):
    monkeypatch.setattr(box, "IDENTITY_MIN", 5)
    mine = photos(5)
    local = mac_photos(tmp_path, mine)
    rented(box, fake)
    fake.box_chips = dict(mine)
    lost = sorted(mine)[2]
    fake.box_missing = [(lost,)]  # one transient failure on the first attempt; the second fetch gets it
    assert box.identity_check(local, sleep=NOSLEEP) == 5 and fake.instances
    assert sum("--limit 50 --seed 0" in c[-1] for c in fake.calls if c[0] == "ssh") == 2
    for f in (fake.remote / "data" / "chips").glob("*.npy"):
        f.unlink()
    fake.box_missing = [(lost,), (lost,)]  # it never arrives: all the others are identical
    with pytest.raises(box.BoxError, match="only 4 of the photos .* nothing differed, the box is still up"):
        box.identity_check(local, sleep=NOSLEEP)
    assert fake.instances and box.load_history() == []  # not destroyed
    np.save(local / "a_county_chip_added_later.npy", np.ones((4, 8, 8), dtype=np.uint8))  # the Mac holds more photos
    assert box.identity_check(local, sleep=NOSLEEP) == 5  # compared on the photos both machines have


def test_c15c_the_speed_trial_limits_every_run_and_picks_the_fastest(box, fake):
    rented(box, fake)
    got = box.speed_trial(sleep=NOSLEEP)
    assert got["best_workers"] == 64 and set(got["rates"]) == {32, 64, 128}
    assert [got["rates"][w] for w in (32, 64, 128)] == pytest.approx([40.0, 80.0, 60.0], rel=0.02)  # log rounds seconds
    trials = [c[-1] for c in fake.calls if c[0] == "ssh" and "src.pipeline.chips" in c[-1]]
    assert len(trials) == 3 and all("--limit 500" in t for t in trials)  # none of them is a statewide fetch
    assert [re.search(r"--seed (\d+) --workers (\d+)", t).groups() for t in trials] == [("1", "32"), ("2", "64"), ("3", "128")]
    with pytest.raises(box.BoxError, match="measured nothing .* the box is untouched"):
        box.speed_trial(sleep=NOSLEEP)  # run again: the photos are already there, the rates would all be 0
    assert fake.instances and box.load_history() == []  # a good box is not destroyed for that
    fake.trials_done.clear()
    fake.trial_rates = {32: 5.0, 64: 19.9, 128: 12.0}
    with pytest.raises(box.BoxError, match="under 20"):
        box.speed_trial(sleep=NOSLEEP)
    assert not fake.instances and box.load_history()[-1]["closed_reason"] == "too slow"


# ---------------------------------------------------------------- status and the command line

def test_status_reports_spend_and_time_left(box, fake):
    rented(box, fake, now=0.0, dph_total=1.0)
    s = box.status(now=1800.0)
    assert s["spent_total"] == 0.5 and s["cap_left"] == 14.5 and s["minutes_to_deadline"] == 450.0


def test_the_command_line_runs_the_same_functions(box, fake, capsys):
    fake.offers = [good_offer(id=41), good_offer(id=42, machine_id=101, dph_total=0.7)]
    box.main(["offers"])
    assert capsys.readouterr().out.splitlines()[0].startswith("42 $0.700/h RTX 5090")
    box.main(["rent"])
    assert "rented instance" in capsys.readouterr().out and len(fake.instances) == 1
    assert fake.created()[0][3] == "42"  # the cheapest European offer
    box.main(["selfstop-test"])
    box.main(["run", "fetch", "true"])
    job = box.load_state()["jobs"]["fetch"]
    fake.rc[job] = 0
    with pytest.raises(SystemExit) as e:
        box.main(["wait", "fetch", "--poll", "1"])
    assert e.value.code == 0
    capsys.readouterr()
    box.main(["status"])
    shown = json.loads(capsys.readouterr().out)
    assert shown["instance_id"] == box.load_state()["instance_id"] and shown["watchdog_armed"] is True
    box.main(["stop"])
    box.main(["start"])
    with pytest.raises(box.BoxError, match="holds no results"):
        box.main(["teardown"])
    box.main(["teardown", "--force-discard"])
    assert not fake.instances
