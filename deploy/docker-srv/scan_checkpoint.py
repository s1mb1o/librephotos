"""Inspect, drain, and verify a LibrePhotos catalog during image replacement.

Run inside the application image. Mount the private checkpoint at /deployment.
The quiesce action runs in the live container before it is stopped.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "librephotos.settings.production")
import django

django.setup()
import psutil
from api.jobs.broker import LEASE
from api.models import LongRunningJob, Photo, Thumbnail
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.utils import timezone
from django_q.models import OrmQ
from django_q.signing import SignedPackage

ROOT = Path(os.environ.get("LP_CHECKPOINT_DIR", "/deployment"))
# These jobs queue one durable task per item and acknowledge each completed item.
DRAINABLE_JOBS = (
    LongRunningJob.JOB_SCAN_PHOTOS,
    LongRunningJob.JOB_GENERATE_TAGS,
    LongRunningJob.JOB_GENERATE_CAPTIONS,
)


def clusters() -> list[dict[str, int]]:
    found = []
    for process in psutil.process_iter():
        try:
            command = process.cmdline()
            if "qcluster" in command and any(
                Path(part).name == "manage.py" for part in command
            ):
                found.append({"pid": process.pid, "ppid": process.ppid()})
        except psutil.Error:
            continue
    return found


def scan_state() -> dict:
    jobs = list(
        LongRunningJob.objects.filter(finished=False).values(
            "job_id",
            "job_type",
            "started_at",
            "progress_current",
            "progress_target",
            "cancelled",
            "failed",
        )
    )
    queued = {str(job["job_id"]): 0 for job in jobs}
    for payload in OrmQ.objects.values_list("payload", flat=True).iterator(
        chunk_size=500
    ):
        task = SignedPackage.loads(payload)
        values = [*task.get("args", ()), task.get("kwargs", {}).get("job_id")]
        identifiers = {
            str(value) for value in values if isinstance(value, (str, uuid.UUID))
        }
        for identifier in identifiers.intersection(queued):
            queued[identifier] += 1
    for job in jobs:
        job["job_id"] = str(job["job_id"])
        job["started_at"] = str(job["started_at"]) if job["started_at"] else None
        job["queued_tasks"] = queued[job["job_id"]]
    return {
        "photos": Photo.objects.count(),
        "jobs": jobs,
        "queue_count": OrmQ.objects.count(),
        "held": OrmQ.objects.filter(lock__gt=timezone.now()).count(),
        "clusters": clusters(),
    }


def check_scans(state: dict) -> None:
    for job in state["jobs"]:
        if not job["started_at"]:
            continue
        if job["job_type"] not in DRAINABLE_JOBS:
            raise RuntimeError(
                "A started job other than a photo scan, tag generation, or caption generation is active. Wait for it before deployment."
            )
        if job["progress_current"] + job["queued_tasks"] != job["progress_target"]:
            raise RuntimeError(
                "The scan is not at a durable queue boundary. Refusing replacement."
            )


def defer_available(frozen: set[int]) -> None:
    """Lease pending rows without blocking the pusher's feeder thread."""
    with transaction.atomic():
        ids = list(
            OrmQ.objects.select_for_update()
            .filter(lock__lte=timezone.now())
            .values_list("pk", flat=True)
        )
        for offset in range(0, len(ids), 500):
            OrmQ.objects.filter(pk__in=ids[offset : offset + 500]).update(
                lock=timezone.now() + LEASE
            )
        frozen.update(ids)


def release_barrier(frozen: set[int]) -> None:
    ids = list(frozen)
    for offset in range(0, len(ids), 500):
        OrmQ.objects.filter(pk__in=ids[offset : offset + 500]).update(
            lock=timezone.now() - datetime.timedelta(seconds=1)
        )


def quiesce(timeout: float = 1200) -> None:
    before = scan_state()
    for job in before["jobs"]:
        if job["started_at"] and job["job_type"] not in DRAINABLE_JOBS:
            raise RuntimeError(
                "A started job other than a photo scan, tag generation, or caption generation is active."
            )
    processes = before["clusters"]
    pids = {process["pid"] for process in processes}
    roots = [process for process in processes if process["ppid"] not in pids]
    if len(roots) > 1:
        raise RuntimeError(
            "Multiple queue clusters found. Refusing an ambiguous drain."
        )
    print(json.dumps({"phase": "draining", "state": before}), flush=True)
    deadline = time.monotonic() + timeout
    frozen: set[int] = set()
    renewed = 0.0
    try:
        while True:
            defer_available(frozen)
            active = set(OrmQ.objects.values_list("pk", flat=True)) - frozen
            if time.monotonic() - renewed >= 30:
                # Keep the barrier alive even when the broker clamps long leases.
                ids = list(frozen | active)
                for offset in range(0, len(ids), 500):
                    OrmQ.objects.filter(pk__in=ids[offset : offset + 500]).update(
                        lock=timezone.now() + LEASE
                    )
                renewed = time.monotonic()
                print(
                    json.dumps(
                        {
                            "phase": "drain-progress",
                            "active_tasks": len(active),
                            "deferred_tasks": len(frozen),
                        }
                    ),
                    flush=True,
                )
            if not active:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("The prefetched queue is still draining.")
            time.sleep(2)
        if roots:
            os.kill(roots[0]["pid"], signal.SIGTERM)
        while clusters():
            defer_available(frozen)
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "The queue is still stopping. Do not replace the container."
                )
            time.sleep(2)
    finally:
        # On error the old cluster can take pending work again. Payloads are untouched.
        release_barrier(frozen)
    after = scan_state()
    check_scans(after)
    print(json.dumps({"phase": "drained", "state": after}), flush=True)


def table_digest(table: str, fields: list[str], primary: str) -> dict:
    digest = hashlib.sha256()
    quoted = connection.ops.quote_name
    names = ", ".join(quoted(field) for field in fields)
    sql = f"SELECT row_to_json(saved)::text FROM (SELECT {names} FROM {quoted(table)} ORDER BY {quoted(primary)}) saved"
    count = 0
    with connection.cursor() as cursor:
        cursor.execute(sql)
        while rows := cursor.fetchmany(500):
            for row in rows:
                digest.update(row[0].encode())
                digest.update(b"\n")
                count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def layout() -> dict:
    tables = set(connection.introspection.table_names())
    result = {}
    for model in apps.get_app_config("api").get_models(include_auto_created=True):
        if model._meta.db_table in tables:
            result[model._meta.db_table] = {
                "fields": [field.column for field in model._meta.concrete_fields],
                "primary": model._meta.pk.column,
            }
    result[OrmQ._meta.db_table] = {
        "fields": [field.column for field in OrmQ._meta.concrete_fields],
        "primary": OrmQ._meta.pk.column,
    }
    return result


def snapshot(specification: dict) -> dict:
    return {
        table: table_digest(table, spec["fields"], spec["primary"])
        for table, spec in sorted(specification.items())
    }


def write(name: str, value: dict) -> None:
    path = ROOT / name
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")
    path.chmod(0o600)


def media_samples() -> list[dict]:
    paths = [
        Path(settings.MEDIA_ROOT) / name
        for name in Thumbnail.objects.exclude(thumbnail_big="")
        .order_by("photo_id")
        .values_list("thumbnail_big", flat=True)[:6]
    ]
    paths += [
        Path(name)
        for name in Photo.objects.filter(main_file__isnull=False)
        .order_by("pk")
        .values_list("main_file__path", flat=True)[:4]
    ]
    result = []
    for path in paths:
        if path.is_file():
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            result.append(
                {"path": str(path), "size": path.stat().st_size, "sha256": digest}
            )
    assert result, "No media samples were readable"
    return result


def verify_media(saved: list[dict]) -> None:
    for item in saved:
        path = Path(item["path"])
        assert path.is_file() and path.stat().st_size == item["size"]
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"]


def before() -> None:
    state = scan_state()
    check_scans(state)
    specification = layout()
    write(
        "before.json",
        {
            "state": state,
            "layout": specification,
            "tables": snapshot(specification),
            "media_samples": media_samples(),
        },
    )
    print(
        json.dumps(
            {
                "phase": "checkpointed",
                "photos": state["photos"],
                "queue_count": state["queue_count"],
                "jobs": state["jobs"],
            }
        ),
        flush=True,
    )


def migrate_verify() -> None:
    saved = json.loads((ROOT / "before.json").read_text())
    verify_media(saved["media_samples"])
    call_command("migrate", interactive=False, verbosity=1)
    actual = snapshot(saved["layout"])
    different = [
        table for table in saved["tables"] if saved["tables"][table] != actual[table]
    ]
    if different:
        raise RuntimeError(
            "Pre-existing catalog or queue data changed: " + ", ".join(different)
        )
    # The old cluster is gone. Release only leases left by that cluster.
    released = OrmQ.objects.filter(lock__gt=timezone.now()).update(
        lock=timezone.now() - datetime.timedelta(seconds=1)
    )
    state = scan_state()
    check_scans(state)
    assert state["photos"] == saved["state"]["photos"]
    assert state["jobs"] == saved["state"]["jobs"]
    write(
        "migrated.json",
        {
            "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tables_preserved": len(actual),
            "released_leases": released,
            "state": state,
        },
    )
    print(
        json.dumps(
            {
                "phase": "migration-verified",
                "tables_preserved": len(actual),
                "photos": state["photos"],
                "queue_count": state["queue_count"],
                "released_leases": released,
            }
        ),
        flush=True,
    )


def after() -> None:
    saved = json.loads((ROOT / "before.json").read_text())
    verify_media(saved["media_samples"])
    state = scan_state()
    assert state["photos"] >= saved["state"]["photos"]
    progress = []
    for old in saved["state"]["jobs"]:
        if old["job_type"] not in DRAINABLE_JOBS or not old["started_at"]:
            continue
        current = LongRunningJob.objects.get(job_id=old["job_id"])
        assert not current.cancelled
        assert current.failed == old["failed"]
        assert current.progress_target == old["progress_target"]
        assert current.progress_current >= old["progress_current"]
        assert str(current.started_at) == old["started_at"]
        progress.append(
            {
                "job_id": old["job_id"],
                "before": old["progress_current"],
                "now": current.progress_current,
                "target": current.progress_target,
                "finished": current.finished,
                "advanced": current.finished
                or current.progress_current > old["progress_current"],
            }
        )
    write(
        "after.json",
        {
            "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "photos": state["photos"],
            "progress": progress,
            "state": state,
        },
    )
    print(
        json.dumps(
            {"phase": "resumed", "photos": state["photos"], "progress": progress}
        ),
        flush=True,
    )


if __name__ == "__main__":
    actions = {
        "quiesce": quiesce,
        "before": before,
        "migrate-verify": migrate_verify,
        "after": after,
        "status": lambda: print(json.dumps(scan_state()), flush=True),
    }
    actions[sys.argv[1]]()
