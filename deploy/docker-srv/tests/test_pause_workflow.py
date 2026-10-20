import json
import runpy
import subprocess
import sys
import time
import threading
from pathlib import Path

import django

if not Path("/tmp/scan_checkpoint.py").is_file():
    raise SystemExit(
        "Run this exercise only in the disposable container documented in README.md"
    )

django.setup()
from api.jobs.queue import enqueue_task
from api.models import LongRunningJob, User
from django.core.management import call_command
from django.db import connections
from django.utils import timezone
from django_q.models import OrmQ
from pause_test_tasks import process_group

call_command("migrate", interactive=False, verbosity=0)
module = runpy.run_path("/tmp/scan_checkpoint.py")
kind = sys.argv[1] if len(sys.argv) > 1 else "scan"
if kind not in {"scan", "tags", "captions"}:
    raise SystemExit("Use scan, tags, or captions")
user = User.objects.create_user(username="pause-test-" + kind, password="isolated-test")
job_type = {
    "scan": LongRunningJob.JOB_SCAN_PHOTOS,
    "tags": LongRunningJob.JOB_GENERATE_TAGS,
    "captions": LongRunningJob.JOB_GENERATE_CAPTIONS,
}[kind]
job = LongRunningJob.create_job(user, job_type, start_now=True)
target = 80
padding = "x" * 65536
job.update_progress(current=0, target=target)
for _ in range(target - 1):
    enqueue_task(process_group, job.job_id, padding)
log = Path("/tmp/pause-test-qcluster-" + kind + ".log")


def start():
    with log.open("ab") as stream:
        return subprocess.Popen(
            [sys.executable, "manage.py", "qcluster"],
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


first = start()
deadline = time.monotonic() + 90
while OrmQ.objects.filter(lock__gt=timezone.now()).count() < 52:
    if time.monotonic() > deadline:
        raise TimeoutError("No prefetched tasks")
    time.sleep(0.1)
prefetched_before = OrmQ.objects.filter(lock__gt=timezone.now()).count()
assert prefetched_before >= 50
try:
    module["quiesce"](timeout=0)
except TimeoutError:
    pass
else:
    raise AssertionError("The forced drain timeout did not run")
assert first.poll() is None
assert OrmQ.objects.filter(lock__lte=timezone.now()).exists()
late_errors = []


def enqueue_late():
    try:
        time.sleep(0.5)
        enqueue_task(process_group, job.job_id, padding)
    except Exception as error:
        late_errors.append(error)
    finally:
        connections.close_all()


late = threading.Thread(target=enqueue_late)
late.start()
module["quiesce"](timeout=60)
late.join(timeout=10)
assert not late.is_alive() and not late_errors
first.wait(timeout=20)
state = module["scan_state"]()
module["check_scans"](state)
job.refresh_from_db()
paused = job.progress_current
assert paused > 0 and paused < target
assert job.progress_current + OrmQ.objects.count() == target
assert "recycled worker" in log.read_text()
released = OrmQ.objects.filter(lock__gt=timezone.now()).update(lock=timezone.now())
second = start()
deadline = time.monotonic() + 90
while True:
    job.refresh_from_db()
    if job.progress_current == target and OrmQ.objects.count() == 0:
        break
    if time.monotonic() > deadline:
        raise TimeoutError("The scan did not finish after resume")
    time.sleep(0.2)
assert not job.cancelled and not job.failed
job.complete()
module["quiesce"](timeout=60)
second.wait(timeout=20)
print(
    json.dumps(
        {
            "isolated_pause_resume_passed": True,
            "job_kind": kind,
            "recycle_every": 2,
            "prefetch_limit": 50,
            "prefetched_before": prefetched_before,
            "failure_cleanup_passed": True,
            "payload_bytes": len(padding),
            "late_enqueue": True,
            "paused_progress": paused,
            "remaining_at_pause": target - paused,
            "final_progress": job.progress_current,
            "target": target,
            "released_leases": released,
            "worker_recycles": log.read_text().count("recycled worker"),
            "production_network_access": False,
        }
    ),
    flush=True,
)
