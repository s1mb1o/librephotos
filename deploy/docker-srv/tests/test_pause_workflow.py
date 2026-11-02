import json
import runpy
import subprocess
import sys
import time
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
from django.utils import timezone
from django_q.models import OrmQ
from pause_test_tasks import process_group

call_command("migrate", interactive=False, verbosity=0)
module = runpy.run_path("/tmp/scan_checkpoint.py")
kind = sys.argv[1] if len(sys.argv) > 1 else "scan"
if kind not in {"scan", "tags"}:
    raise SystemExit("Use scan or tags")
user = User.objects.create_user(username="pause-test-" + kind, password="isolated-test")
job_type = (
    LongRunningJob.JOB_GENERATE_TAGS
    if kind == "tags"
    else LongRunningJob.JOB_SCAN_PHOTOS
)
job = LongRunningJob.create_job(user, job_type, start_now=True)
job.update_progress(current=0, target=20)
for _ in range(20):
    enqueue_task(process_group, job.job_id)
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
while OrmQ.objects.filter(lock__gt=timezone.now()).count() < 4:
    if time.monotonic() > deadline:
        raise TimeoutError("No prefetched tasks")
    time.sleep(0.1)
module["quiesce"]()
first.wait(timeout=20)
state = module["scan_state"]()
module["check_scans"](state)
job.refresh_from_db()
paused = job.progress_current
assert paused > 0 and paused < 20
assert job.progress_current + OrmQ.objects.count() == 20
assert "recycled worker" in log.read_text()
released = OrmQ.objects.filter(lock__gt=timezone.now()).update(lock=timezone.now())
second = start()
deadline = time.monotonic() + 90
while True:
    job.refresh_from_db()
    if job.progress_current == 20 and OrmQ.objects.count() == 0:
        break
    if time.monotonic() > deadline:
        raise TimeoutError("The scan did not finish after resume")
    time.sleep(0.2)
assert not job.cancelled and not job.failed
job.complete()
module["quiesce"]()
second.wait(timeout=20)
print(
    json.dumps(
        {
            "isolated_pause_resume_passed": True,
            "job_kind": kind,
            "recycle_every": 2,
            "prefetch_limit": 6,
            "paused_progress": paused,
            "remaining_at_pause": 20 - paused,
            "final_progress": job.progress_current,
            "target": 20,
            "released_leases": released,
            "worker_recycles": log.read_text().count("recycled worker"),
            "production_network_access": False,
        }
    ),
    flush=True,
)
