"""Load test for AMG-NF-005 (TC-Perf-02): 100 concurrent users and 20 concurrent processing jobs.

Start the backend on an empty database first (from an empty folder), for example:
    $env:RATE_LIMIT_ENABLED='false'; uvicorn app.main:app --app-dir <backend> --port 8001
Then:
    python scripts/loadcheck.py --base http://127.0.0.1:8001 --audio ../eval/recordings/quiet_room.wav

The per-address login limit (10 a minute) would stop 100 test users logging in from one machine, so the
server is started with RATE_LIMIT_ENABLED=false for this test. Results go to ../docs/scalability/results.json.
"""
import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:8001")
ap.add_argument("--audio", required=True)
ap.add_argument("--users", type=int, default=100)
ap.add_argument("--jobs", type=int, default=20)
ap.add_argument("--rounds", type=int, default=5)
ap.add_argument("--job-timeout", type=int, default=3600)
ap.add_argument("--out", default="../docs/scalability/results.json")
args = ap.parse_args()

PASSWORD = "load-test-123"
audio_bytes = Path(args.audio).read_bytes()
lock = threading.Lock()


def client():
    return httpx.Client(base_url=args.base, timeout=120)


def pct(values, p):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(len(values) * p / 100))], 3)


def summarise(samples):
    """samples: list of (status_code or 'error', seconds)."""
    times = [s for _, s in samples]
    failed = [c for c, _ in samples if not (isinstance(c, int) and c < 400)]
    return {
        "requests": len(samples), "failed": len(failed), "failed_codes": sorted(set(map(str, failed))),
        "mean_s": round(statistics.mean(times), 3) if times else None,
        "p50_s": pct(times, 50), "p95_s": pct(times, 95), "max_s": round(max(times), 3) if times else None,
    }


def timed(c, method, url, **kw):
    t = time.perf_counter()
    try:
        r = c.request(method, url, **kw)
        return r, (r.status_code, time.perf_counter() - t)
    except Exception as e:  # noqa: BLE001
        return None, (f"error:{type(e).__name__}", time.perf_counter() - t)


# ---------------------------------------------------------------- set up users
def make_user(i):
    with client() as c:
        email = f"load{i}@example.com"
        c.post("/auth/register", json={"name": f"Load User {i}", "email": email, "password": PASSWORD})
        r = c.post("/auth/login", json={"email": email, "password": PASSWORD})
        r.raise_for_status()
        return {"email": email, "token": r.json()["token"]}


t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=20) as pool:
    users = list(pool.map(make_user, range(args.users)))
setup_s = round(time.perf_counter() - t0, 1)
print(f"{len(users)} users registered and logged in in {setup_s}s")


# ---------------------------------------------------------------- read/write mix by many users at once
def user_session(u, barrier=None):
    samples = []
    h = {"Authorization": f"Bearer {u['token']}"}
    with client() as c:
        if barrier:
            barrier.wait()
        for k in range(args.rounds):
            _, s = timed(c, "GET", "/meetings", headers=h); samples.append(s)
            r, s = timed(c, "POST", "/meetings", headers=h, json={"title": f"Load {u['email']} {k}"}); samples.append(s)
            if r is not None and r.status_code < 300:
                mid = r.json()["id"]
                _, s = timed(c, "GET", f"/meetings/{mid}", headers=h); samples.append(s)
            _, s = timed(c, "GET", "/auth/me", headers=h); samples.append(s)
    return samples


def mixed_load(label):
    barrier = threading.Barrier(len(users))
    t = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(users)) as pool:
        out = [s for chunk in pool.map(lambda u: user_session(u, barrier), users) for s in chunk]
    res = summarise(out)
    res["wall_s"] = round(time.perf_counter() - t, 1)
    print(label, res)
    return res


results = {"users": args.users, "jobs": args.jobs, "rounds": args.rounds, "setup_s": setup_s,
           "audio": Path(args.audio).name, "audio_kb": round(len(audio_bytes) / 1024)}
results["phase_a_100_users"] = mixed_load("A: 100 users, no jobs running")

# ---------------------------------------------------------------- 20 jobs at once
job_users = users[: args.jobs]
job_info = {}


def submit(i):
    u = job_users[i]
    h = {"Authorization": f"Bearer {u['token']}"}
    with client() as c:
        r = c.post("/meetings", headers=h, json={"title": f"Job {i}", "attendees": [{"name": "A", "email": u["email"]}]})
        mid = r.json()["id"]
        r = c.post(f"/meetings/{mid}/audio", headers=h, files={"file": ("clip.wav", audio_bytes, "audio/wav")})
        up = r.status_code
        barrier_jobs.wait()
        t = time.perf_counter()
        r = c.post(f"/meetings/{mid}/process", headers=h)
        with lock:
            job_info[i] = {"meeting_id": mid, "upload_status": up, "process_status": r.status_code,
                           "accept_s": round(time.perf_counter() - t, 3), "token": u["token"]}


barrier_jobs = threading.Barrier(args.jobs)
t_submit = time.perf_counter()
with ThreadPoolExecutor(max_workers=args.jobs) as pool:
    list(pool.map(submit, range(args.jobs)))
accepted = sum(1 for v in job_info.values() if v["process_status"] == 202)
results["jobs_submitted_at_once"] = {
    "accepted_202": accepted, "rejected": args.jobs - accepted,
    "process_statuses": sorted({v["process_status"] for v in job_info.values()}),
    "upload_statuses": sorted({v["upload_status"] for v in job_info.values()}),
    "max_accept_s": max(v["accept_s"] for v in job_info.values()),
}
print("jobs:", results["jobs_submitted_at_once"])

# the same 100 users keep using the app while 19 or 20 jobs are queued
results["phase_b_100_users_while_jobs_queued"] = mixed_load("B: 100 users while jobs are queued")

# wait for every job
done = {}
deadline = time.time() + args.job_timeout
while len(done) < args.jobs and time.time() < deadline:
    for i, v in job_info.items():
        if i in done:
            continue
        try:
            r = httpx.get(f"{args.base}/meetings/{v['meeting_id']}/status", headers={"Authorization": f"Bearer {v['token']}"}, timeout=60)
            st = r.json().get("status")
        except Exception:  # noqa: BLE001
            continue
        if st in ("READY", "FAILED"):
            done[i] = {"status": st, "after_s": round(time.perf_counter() - t_submit, 1),
                       "error": r.json().get("error")}
    time.sleep(5)
results["jobs_finished"] = {
    "ready": sum(1 for d in done.values() if d["status"] == "READY"),
    "failed": sum(1 for d in done.values() if d["status"] == "FAILED"),
    "still_running_at_timeout": args.jobs - len(done),
    "first_done_s": min((d["after_s"] for d in done.values()), default=None),
    "last_done_s": max((d["after_s"] for d in done.values()), default=None),
    "failures": [d["error"] for d in done.values() if d["status"] == "FAILED"][:5],
}
print("finished:", results["jobs_finished"])

out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(results, indent=2), encoding="utf-8")
print("saved", out.resolve())
