"""Cloud box driver (scripts/cloud/box.py). vast.ai and ssh are replaced by a small fake; nothing is rented."""

import json
import re
import types

import pytest

from vision_helpers import good_offer

NOSLEEP = lambda s: None  # noqa: E731


def reply(rc=0, out="", err=""):
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


class Fake:
    """Stands in for box._sh: a tiny vast.ai backend plus canned ssh answers."""

    def __init__(self):
        self.calls, self.instances, self.next_id = [], {}, 5000
        self.create_status = "running"
        self.destroy_works = self.has_key = self.selfstop_works = self.start_works = True
        self.watchdog = self.launch_ok = True
        self.ssh_fail_times = 0
        self.rc = {}
        self.offers = []
        self.on_call = None

    def __call__(self, args, timeout=600, input=None, stdin=None, stdout=None):
        self.calls.append(list(args))
        if self.on_call:
            self.on_call(args)
        if args[0] == "vastai":
            return self.vast(args[1:])
        if args[0] == "ssh":
            return self.ssh(args[-1])
        raise AssertionError(f"unexpected command {args}")

    def vast(self, a):
        if a[:2] == ["show", "instances-v1"]:
            return reply(out=json.dumps({"instances": list(self.instances.values())}))
        if a[:2] == ["create", "instance"]:
            self.next_id += 1
            self.instances[self.next_id] = {"id": self.next_id, "actual_status": self.create_status,
                                            "ssh_host": "ssh.example", "ssh_port": 2222}
            return reply(out=json.dumps({"new_contract": self.next_id}))
        if a[:2] == ["destroy", "instance"]:
            if self.destroy_works:
                self.instances.pop(int(a[2]), None)
            return reply()
        if a[:2] == ["stop", "instance"]:
            self.instances[int(a[2])]["actual_status"] = "exited"
            return reply()
        if a[:2] == ["start", "instance"]:
            if self.start_works:
                self.instances[int(a[2])]["actual_status"] = "running"
            return reply()
        if a[:2] == ["search", "offers"]:
            return reply(out=json.dumps(self.offers))
        if a[:2] == ["label", "instance"]:
            self.instances[int(a[2])]["label"] = a[3]
            return reply()
        raise AssertionError(f"unexpected vastai call {a}")

    def ssh(self, cmd):
        if self.ssh_fail_times > 0:
            self.ssh_fail_times -= 1
            return reply(rc=255, err="Connection refused")
        if "echo HAVE_KEY" in cmd:
            return reply(out="HAVE_KEY\n") if self.has_key else reply(rc=1)
        if "vastai stop instance $CONTAINER_ID" in cmd:
            if self.selfstop_works:
                for inst in self.instances.values():
                    inst["actual_status"] = "exited"
            return reply()
        if "echo ALIVE" in cmd:
            return reply(out="ALIVE\n") if self.watchdog else reply(rc=1)
        if "echo LAUNCHED" in cmd:
            return reply(out="LAUNCHED\n") if self.launch_ok else reply(rc=1)
        if "echo RC=" in cmd:
            job = re.search(r"logs/([\w\-]+)\.rc", cmd).group(1)
            code = self.rc.get(job)
            return reply(out=f"RC={'' if code is None else code}\nlast log line\n")
        return reply()


@pytest.fixture
def fake(box, monkeypatch):
    f = Fake()
    f.now = 1000.0
    monkeypatch.setattr(box, "_sh", f)
    monkeypatch.setattr(box, "_now", lambda: f.now)  # the driver's clock
    monkeypatch.setattr(box, "high_ports_reachable", lambda: True)  # no real network in tests
    return f


def rented(box, fake, now=1000.0, **offer_changes):
    fake.now = now
    return box.rent(good_offer(**offer_changes), sleep=NOSLEEP)


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


def test_c22b_the_4090_fallback_is_used_only_when_no_5090_matches(box, fake):
    fake.offers = [good_offer(id=9, gpu_name="RTX 4090", gpu_ram=24564)]
    assert [o["id"] for o in box.pick_offers()] == [9]
    fake.offers = []
    with pytest.raises(ValueError):
        box.pick_offers()


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
    assert not fake.instances and not any(c[1:3] == ["create", "instance"] for c in fake.calls)
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
    assert state["deadline_epoch"] == pytest.approx(now + 6 * 3600)  # $12 at $2/h, not the 8-hour limit
    assert box.spent_total(now + 3600.0) == pytest.approx(5.0)


# ---------------------------------------------------------------- renting and failure exits (C7, C8, C19)

def test_c7_the_instance_id_is_saved_before_setup_starts(box, fake):
    seen = []

    def spy(args):
        if args[:3] == ["vastai", "show", "instances-v1"] or args[0] == "ssh":
            seen.append(box.STATE.exists() and box.load_state()["instance_id"])

    fake.on_call = spy
    state = rented(box, fake)
    assert seen and all(s == state["instance_id"] for s in seen)
    assert state["ssh_host"] == "ssh.example" and state["ssh_port"] == 2222


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
    monkey_sleep = NOSLEEP
    orig = box.ssh
    box.ssh = lambda cmd, **kw: orig(cmd, **{**kw, "sleep": monkey_sleep})
    with pytest.raises(box.BoxError, match="ssh failed"):
        rented(box, fake)
    assert not fake.instances and box.load_history()[0]["closed_reason"] == "ssh unreachable"


def test_c19c_a_third_replacement_is_refused(box, fake):
    fake.create_status = "loading"
    for _ in range(3):  # the first box and two replacements
        with pytest.raises(box.BoxError, match="never reached running"):
            rented(box, fake)
    fake.create_status = "running"
    n_created = sum(c[1:3] == ["create", "instance"] for c in fake.calls)
    with pytest.raises(box.BoxError, match="no further replacement"):
        rented(box, fake)
    assert sum(c[1:3] == ["create", "instance"] for c in fake.calls) == n_created == 3


def test_c19d_gpu_or_memory_check_failure_destroys_the_box(box, fake):
    rented(box, fake)
    with pytest.raises(box.BoxError, match="GPU is not usable"):
        box.setup()  # the fake prints no GPU line
    assert not fake.instances and box.load_history()[-1]["closed_reason"] == "gpu check"
    rented(box, fake, now=2000.0)
    with pytest.raises(box.BoxError, match="does not fit"):
        box.memcheck()
    assert not fake.instances and box.load_history()[-1]["closed_reason"] == "memory check"


def test_c8_teardown_raises_if_the_instance_is_still_listed(box, fake):
    rented(box, fake)
    fake.destroy_works = False
    with pytest.raises(box.BoxError, match="still listed"):
        box.teardown(force_discard=True, sleep=NOSLEEP)
    assert box.load_state() is not None  # not booked as gone


def test_c9_teardown_refuses_unverified_results_unless_forced(box, fake):
    state = rented(box, fake)
    state["last_run_at"], state["last_verified_pull_at"] = 2000.0, 1500.0
    box.save_state(state)
    with pytest.raises(box.BoxError, match="pull first"):
        box.teardown(sleep=NOSLEEP)
    assert fake.instances
    state["last_verified_pull_at"] = 2500.0
    box.save_state(state)
    box.teardown(now=3000.0, sleep=NOSLEEP)
    assert not fake.instances and box.load_state() is None
    assert box.load_history()[-1]["closed_reason"] == "done"
    assert box.abandoned_count() == 0


def test_c9b_forced_teardown_discards(box, fake):
    state = rented(box, fake)
    state["last_run_at"] = 2000.0
    box.save_state(state)
    box.teardown(force_discard=True, now=3000.0, sleep=NOSLEEP)
    assert not fake.instances


def test_c24_renting_is_refused_on_a_network_that_blocks_high_ports(box, fake, monkeypatch):
    monkeypatch.setattr(box, "high_ports_reachable", lambda: False)
    with pytest.raises(box.BoxError, match="blocks outgoing connections on high ports"):
        rented(box, fake)
    assert not fake.instances and box.load_state() is None and box.load_history() == []
    assert not any(c[1:3] == ["create", "instance"] for c in fake.calls)  # nothing rented, nothing charged


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


def test_c25_a_rented_box_is_labelled_and_teardown_touches_only_its_own_id(box, fake):
    fake.instances[777] = {"id": 777, "actual_status": "running", "ssh_host": "other", "ssh_port": 1}  # another chat's box
    state = rented(box, fake)
    assert fake.instances[state["instance_id"]]["label"] == box.LABEL == "image-augmentation"
    box.teardown(force_discard=True, sleep=NOSLEEP)
    assert list(fake.instances) == [777]  # ours is gone; the other one was never touched
    touched = [c for c in fake.calls if c[0] == "vastai" and c[1] in ("destroy", "stop", "start", "label")]
    assert all(int(c[3]) == state["instance_id"] for c in touched)


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


def test_c23c_a_working_self_stop_restarts_and_arms_the_watcher(box, fake):
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


def test_c23e_the_watcher_script_waits_for_the_fixed_deadline_then_stops_the_box(box):
    script = box.watchdog_script(1234567.9)
    assert "-lt 1234567 ]" in script
    assert script.index("pkill") < script.index("vastai stop instance $CONTAINER_ID")


def test_c20_launching_a_job_is_refused_without_the_deadline_watcher(box, fake):
    rented(box, fake)
    fake.watchdog = False
    with pytest.raises(box.BoxError, match="deadline watcher"):
        box.run("fetch", "true", sleep=NOSLEEP)
    assert box.load_state()["jobs"] == {}


def test_stop_and_start_switch_the_billing_rate_and_rearm(box, fake):
    state = rented(box, fake, now=0.0)
    box.stop(now=3600.0, sleep=NOSLEEP)
    assert box.load_state()["watchdog_armed"] is False
    box.start(now=7200.0, sleep=NOSLEEP)
    s = box.load_state()
    assert s["watchdog_armed"] is True and s["deadline_epoch"] == state["deadline_epoch"]  # never extended
    assert box.rental_cost(s, 7200.0) == pytest.approx(state["dph"] + state["storage_rate"])


# ---------------------------------------------------------------- jobs (C16, C17)

def test_c16_a_rerun_gets_a_new_id_and_never_reads_the_old_exit_status(box, fake):
    rented(box, fake)
    first = box.run("fetch", "true", now=1_700_000_000.0, sleep=NOSLEEP)
    fake.rc[first] = 0
    assert box.job_status("fetch")[0] == 0
    second = box.run("fetch", "true", now=1_700_000_060.0, sleep=NOSLEEP)
    assert second != first and box.load_state()["jobs"]["fetch"] == second
    assert box.job_status("fetch")[0] is None  # the earlier run's exit status is not reported
    fake.rc[second] = 3
    assert box.wait("fetch", sleep=NOSLEEP) == 3
    launch = [c[-1] for c in fake.calls if c[0] == "ssh" and "setsid nohup" in c[-1] and second in c[-1]][0]
    assert f"{second}.rc.tmp" in launch and f"mv logs/{second}.rc.tmp logs/{second}.rc" in launch
    assert "mkdir -p logs" in launch


def test_c17_a_job_that_fails_to_launch_raises(box, fake):
    rented(box, fake)
    fake.launch_ok = False
    with pytest.raises(box.BoxError, match="did not start"):
        box.run("fetch", "true", sleep=NOSLEEP)
    assert "fetch" not in box.load_state()["jobs"]


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


def test_c13b_a_failing_remote_command_is_not_retried(box, fake, monkeypatch):
    rented(box, fake)
    monkeypatch.setattr(fake, "ssh", lambda cmd: reply(rc=2, err="boom"))
    fake.calls.clear()
    with pytest.raises(box.BoxError, match="remote command failed"):
        box.ssh("false", sleep=NOSLEEP)
    assert len(fake.calls) == 1


# ---------------------------------------------------------------- shipping (C10, C11, C12)

def make_project(root):
    for rel, text in {"src/a.py": "x = 1\n", "src/model/b.py": "y = 2\n", "tests/vision/test_x.py": "z = 3\n",
                      "scripts/cloud/box.py": "w = 4\n", "pyproject.toml": "[project]\n", "uv.lock": "lock\n",
                      ".python-version": "3.11\n", "data/raw/ncdot_joined.parquet": "p",
                      "data/raw/naip_2022_index.parquet": "q", "src/__pycache__/a.cpython-311.pyc": "junk",
                      "src/a 2.py": "icloud duplicate\n", "data/raw/other.parquet": "not listed"}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def test_c12_the_push_list_holds_only_the_expected_paths(box, tmp_path):
    make_project(tmp_path)
    files = box.bundle_files(tmp_path)
    assert files == sorted([".python-version", "data/raw/naip_2022_index.parquet", "data/raw/ncdot_joined.parquet",
                            "pyproject.toml", "scripts/cloud/box.py", "src/a.py", "src/model/b.py",
                            "tests/vision/test_x.py", "uv.lock"])
    assert all(not e.startswith(("/", "~", "..")) and ".git" not in e and ".config" not in e for e in box.PUSH_LIST)
    (tmp_path / "data/processed").mkdir(parents=True)
    (tmp_path / "data/processed/segments_targets.parquet").write_text("t")
    assert "data/processed/segments_targets.parquet" in box.bundle_files(tmp_path)
    (tmp_path / "uv.lock").unlink()
    with pytest.raises(box.BoxError, match="missing uv.lock"):
        box.bundle_files(tmp_path)


@pytest.mark.parametrize("rel,text", [
    ("src/vast_api_key", "abc"),
    ("src/deploy.pem", "abc"),
    ("src/id_ed25519", "abc"),
    ("src/.env", "A=1"),
    ("src/creds.txt", "secret_access" + "_key=abcdef"),
    ("src/k.py", "-----BEGIN OPENSSH PRIVATE" + " KEY-----"),
    ("src/cfg.toml", "api" + "_key = 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4'"),
])
def test_c11_a_bundle_that_looks_like_it_holds_a_key_is_refused(box, tmp_path, rel, text):
    make_project(tmp_path)
    box.scan_for_keys(box.bundle_files(tmp_path), tmp_path)  # the clean project passes
    (tmp_path / rel).write_text(text)
    with pytest.raises(box.BoxError, match="look like they hold a key"):
        box.scan_for_keys(box.bundle_files(tmp_path) + ([rel] if rel not in box.bundle_files(tmp_path) else []),
                          tmp_path)


def test_c11b_the_real_bundle_holds_no_key(box):
    real = box.ROOT
    files = [f for f in box.bundle_files(real) if not f.endswith(".parquet")]
    box.scan_for_keys(files, real)


def test_c10_a_results_list_that_differs_is_detected(box, tmp_path):
    d = tmp_path / "got"
    (d / "sub").mkdir(parents=True)
    (d / "a.json").write_text("alpha")
    (d / "sub" / "b.npy").write_bytes(b"\x00\x01\x02")
    good = [["a.json", 5, box.file_sha256(d / "a.json")], ["sub/b.npy", 3, box.file_sha256(d / "sub" / "b.npy")]]
    assert box.verify_manifest(good, d) == []
    assert box.verify_manifest(good + [["missing.txt", 1, "0" * 64]], d) == ["missing.txt"]
    assert box.verify_manifest(good[:1], d) == ["sub/b.npy"]  # an extra local file
    assert box.verify_manifest([["a.json", 6, good[0][2]], good[1]], d) == ["a.json"]  # size
    assert box.verify_manifest([["a.json", 5, "f" * 64], good[1]], d) == ["a.json"]  # hash


def test_code_hash_is_stable_and_changes_with_a_file(box, tmp_path):
    make_project(tmp_path)
    h = box.code_hash(tmp_path)
    assert h == box.code_hash(tmp_path) and len(h) == 64
    (tmp_path / "src/a 2.py").write_text("changed duplicate\n")
    assert box.code_hash(tmp_path) == h  # iCloud duplicates are not part of the code
    (tmp_path / "src/model/b.py").write_text("y = 3\n")
    assert box.code_hash(tmp_path) != h
    h2 = box.code_hash(tmp_path)
    (tmp_path / "uv.lock").write_text("other lock\n")
    assert box.code_hash(tmp_path) != h2


# ---------------------------------------------------------------- photo checks (C14, C15)

BANNER = "112,393 chips to cut from 4,012 NAIP tiles with 64 workers (37 midpoints outside NAIP 2022 coverage)\n"
FINAL = "[chips] 112,393/112,393 (100.0%)  80.0 chips/s  12 failed  done in 1404.9s\n"


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


def test_c14b_the_census_must_add_up_and_failures_stay_under_half_a_percent(box):
    parsed = {"to_cut": 49, "uncovered": 37, "done": 49, "failed": 12, "seconds": 5.0}
    assert box.census(112443 - 49, parsed)["on_disk"] == 112394
    with pytest.raises(box.BoxError, match="does not add up"):
        box.census(112443 - 50, parsed)
    many = dict(parsed, failed=563)  # 0.5007% of 112,443
    with pytest.raises(box.BoxError, match="above 0.5%"):
        box.census(112443 - 563 - 37, many)
    box.census(112443 - 562 - 37, dict(parsed, failed=562))  # 0.4998% passes


def test_c15_a_differing_photo_hash_is_detected(box):
    mac = box.parse_digests("a.npy 111\nb.npy 222\nc.npy 333\nnoise line here\n")
    assert mac == {"a.npy": "111", "b.npy": "222", "c.npy": "333"}
    assert box.compare_digests(mac, dict(mac)) == []
    assert box.compare_digests(mac, {**mac, "b.npy": "999"}) == ["b.npy"]
    assert box.compare_digests(mac, {"a.npy": "111", "b.npy": "222"}) == ["c.npy"]  # missing on the box
    extra = dict(mac, **{"d.npy": "444"})
    assert box.compare_digests(mac, extra, names=mac) == []  # only the Mac's photos are compared
    assert box.compare_digests(mac, extra) == ["d.npy"]


def test_c15b_the_digest_code_hashes_pixels_not_file_bytes(box, tmp_path):
    np = pytest.importorskip("numpy")
    arr = np.arange(4 * 8 * 8, dtype=np.uint8).reshape(4, 8, 8)
    np.save(tmp_path / "x.npy", arr)
    import contextlib
    import io
    import sys
    buf, argv = io.StringIO(), sys.argv
    sys.argv = ["digest", str(tmp_path)]
    try:
        with contextlib.redirect_stdout(buf):
            exec(box.DIGEST_PY, {})
    finally:
        sys.argv = argv
    import hashlib
    assert box.parse_digests(buf.getvalue()) == {"x.npy": hashlib.sha256(arr.tobytes()).hexdigest()}


# ---------------------------------------------------------------- status

def test_status_reports_spend_and_time_left(box, fake):
    rented(box, fake, now=0.0, dph_total=1.0)
    s = box.status(now=1800.0)
    assert s["spent_total"] == 0.5 and s["cap_left"] == 14.5 and s["minutes_to_deadline"] == 450.0
