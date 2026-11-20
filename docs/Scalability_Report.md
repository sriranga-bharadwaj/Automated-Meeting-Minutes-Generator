# Scalability Report (AMG-NF-005, TC-Perf-02)

Requirement: the system shall support 100 concurrent users and 20 concurrent processing jobs; excess jobs shall be queued, not rejected. Acceptance: the load test shows no failed requests.

Run on 20-Nov-2026 on one Windows machine with the script `backend/scripts/loadcheck.py`. Raw numbers: `docs/scalability/results.json`.

## Method

- A fresh backend on an empty database (port 8001) with `RATE_LIMIT_ENABLED=false`. The limit of 10 logins a minute per address would stop 100 test users from logging in from one machine, so it was switched off for this test only.
- 100 users registered and logged in (30 s).
- Phase A: all 100 users started together; each made 5 rounds of list meetings, create meeting, open meeting and read own profile (2000 requests).
- Jobs: 20 users each created a meeting, uploaded the same 2.5 MB recording (`eval/recordings/quiet_room.wav`) and started processing at the same moment.
- Phase B: the 100 users repeated phase A while the 20 jobs were queued (2000 requests).
- The script then waited until every job was Ready or Failed.

## Results

| Test | Requests | Failed | Median | 95th percentile | Slowest |
|---|---|---|---|---|---|
| A: 100 users at once | 2000 | 0 | 3.3 s | 9.0 s | 13.0 s |
| B: 100 users while 20 jobs are queued | 2000 | 0 | 5.0 s | 35.0 s | 46.3 s |

- 20 of 20 jobs were accepted (HTTP 202); none was rejected. The slowest answer to "start processing" took 0.2 s.
- All 20 jobs finished Ready, none Failed. The first finished after 4.4 minutes and the last after 26.7 minutes (counted from the moment they were submitted), because one recording is processed at a time (about 80 s each).

Verdict: the acceptance criterion (no failed requests, excess jobs queued and not rejected) is met in this test.

## What the first run found and what was changed

The first run, before any change, failed: of the 1500 requests it completed, all failed (HTTP 500 and timeouts), and the server then stopped answering. The server log showed `QueuePool limit of size 5 overflow 10 reached`. Two causes:

1. The database connection pool allowed only 15 connections.
2. The login-check middleware ran database queries directly on the server's event loop, so when the pool was full the whole server froze, even for requests that needed no database.

Changes (`backend/app/database.py`, `backend/app/auth.py`, `backend/app/main.py`):

- The pool is larger (30 connections plus 70 extra, 60 s wait), and SQLite uses WAL mode with a 30 s busy wait.
- The middleware's database checks now run in a worker thread.
- The meeting list reads only the owners it needs instead of every user.

All 226 backend tests pass after these changes.

## Limits of this test

- One machine ran the server and the 100 simulated users, so timings include the load of the test itself.
- Rate limiting was off. In normal use 10 logins a minute per address apply, so 100 people behind one office address could be slowed at login (HTTP 429).
- Pages are slow under this load: a median of 3 to 5 seconds, and up to 46 seconds while jobs run. The requirement says nothing about response time, so this is reported, not judged.
- Jobs are processed one at a time, so 20 jobs take about 27 minutes. They are queued, not rejected, which is what the requirement asks. Running them in parallel would need a stronger machine and a separate queue (the SAD planned Celery and Redis; they were not built).
- The meeting list still reads every meeting on each call, so it will slow down as the number of meetings grows.
- Job status is kept in memory and is lost if the server restarts.
- Only one recording (2.5 MB) was used.
