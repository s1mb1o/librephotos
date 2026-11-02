"""Replace one image after draining queued work and preserving catalog state."""

import datetime
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

root = Path("/srv/librephotos")
image = sys.argv[1]
if not image.startswith("registry.my.3simbio.ru/librephotos/app:"):
    raise SystemExit("Unexpected image repository")
lock = (root / ".deploy.lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
env_path = root / ".env"
previous = env_path.read_text()
values = dict(
    line.split("=", 1)
    for line in previous.splitlines()
    if line and not line.startswith("#")
)
photo_root = Path(values["LP_PHOTO_ROOT"])
if not (photo_root / "Years").is_dir():
    raise SystemExit("PhotoLibrary is unavailable. Refusing deployment.")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, cwd=root, **kwargs)


def phase(message):
    print(message, flush=True)


def inspect(name, template):
    result = subprocess.run(
        ["docker", "inspect", "--format", template, name],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


helper = root / "bin/scan_checkpoint.py"
assert helper.is_file(), "Missing scan checkpoint helper"
phase("Pulling the replacement image before pausing any work")
run("docker", "pull", image)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
checkpoint = root / "backups" / ("deploy-" + stamp)
checkpoint.mkdir(mode=0o700, parents=True)
shutil.copy2(helper, checkpoint / "scan_checkpoint.py")
shutil.copy2(root / "compose.yaml", checkpoint / "compose.before.yaml")
(checkpoint / "environment.before.private").write_text(previous)
(checkpoint / "environment.before.private").chmod(0o600)
previous_image = values.get("LP_IMAGE")
database_id = inspect("librephotos-db", "{{.Id}}")
checkpointed = False


def catalog(action):
    run(
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "-v",
        str(checkpoint) + ":/deployment",
        "--entrypoint",
        "python",
        "app",
        "/deployment/scan_checkpoint.py",
        action,
    )


try:
    if inspect("librephotos-app", "{{.State.Running}}") == "true":
        phase("Draining the queue cluster without cancelling scan jobs")
        run(
            "docker",
            "cp",
            str(helper),
            "librephotos-app:/tmp/librephotos-scan-checkpoint.py",
        )
        run(
            "docker",
            "exec",
            "librephotos-app",
            "python",
            "/tmp/librephotos-scan-checkpoint.py",
            "quiesce",
        )
        phase("Stopping the application after its worker queue has drained")
        run("docker", "compose", "stop", "--timeout", "30", "app")
    if inspect("librephotos-db", "{{.State.Running}}") != "true":
        run("docker", "compose", "up", "-d", "--wait", "db")
        database_id = inspect("librephotos-db", "{{.Id}}")
    phase("Backing up the frozen catalog")
    backup = checkpoint / "catalog.before.dump"
    with backup.open("xb") as stream:
        os.chmod(backup, 0o600)
        run(
            "docker",
            "exec",
            "librephotos-db",
            "pg_dump",
            "-U",
            "librephotos",
            "-d",
            "librephotos",
            "-Fc",
            stdout=stream,
        )
    with backup.open("rb") as stream:
        run(
            "docker",
            "exec",
            "-i",
            "librephotos-db",
            "pg_restore",
            "--list",
            stdin=stream,
            stdout=subprocess.DEVNULL,
        )
    phase("Recording catalog rows, scan counters, and signed queue payloads")
    catalog("before")
    checkpointed = True
    lines = [line for line in previous.splitlines() if not line.startswith("LP_IMAGE=")]
    temporary = root / ".env.next"
    temporary.write_text("\n".join([*lines, "LP_IMAGE=" + image]) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(env_path)
    run("docker", "compose", "config", "--quiet")
    phase(
        "Applying migrations offline and verifying all pre-existing catalog and queue rows"
    )
    catalog("migrate-verify")
    phase("Starting the new image with the preserved database and queue")
    run(
        "docker",
        "compose",
        "up",
        "-d",
        "--no-deps",
        "--wait",
        "--wait-timeout",
        "600",
        "app",
    )
    assert database_id == inspect("librephotos-db", "{{.Id}}"), (
        "Database container changed"
    )
    username = values.get("LP_ADMIN_USER", "ashmelev")
    probe = subprocess.check_output(
        [
            "docker",
            "exec",
            "librephotos-app",
            "python",
            "manage.py",
            "shell",
            "-c",
            "from api.models import User; print('ADMIN_EXISTS=' + str(int(User.objects.filter(username="
            + repr(username)
            + ").exists())))",
        ],
        text=True,
    )
    if "ADMIN_EXISTS=0" in probe.splitlines():
        bootstrap_env = dict(os.environ)
        bootstrap_env["ADMIN_PASSWORD"] = values["LP_ADMIN_PASSWORD"]
        run(
            "docker",
            "exec",
            "-e",
            "ADMIN_PASSWORD",
            "librephotos-app",
            "python",
            "manage.py",
            "createadmin",
            username,
            values.get("LP_ADMIN_EMAIL", ""),
            env=bootstrap_env,
        )
    temporary_root = "/tmp/librephotos-checkpoint-" + stamp
    run("docker", "exec", "librephotos-app", "mkdir", "-p", temporary_root)
    run(
        "docker",
        "cp",
        str(helper),
        "librephotos-app:" + temporary_root + "/scan_checkpoint.py",
    )
    run(
        "docker",
        "cp",
        str(checkpoint / "before.json"),
        "librephotos-app:" + temporary_root + "/before.json",
    )
    phase("Verifying that the original scan resumes and advances")
    deadline = time.monotonic() + 240
    while True:
        result = run(
            "docker",
            "exec",
            "-e",
            "LP_CHECKPOINT_DIR=" + temporary_root,
            "librephotos-app",
            "python",
            temporary_root + "/scan_checkpoint.py",
            "after",
            capture_output=True,
            text=True,
        )
        resumed = json.loads(result.stdout.strip().splitlines()[-1])
        if all(job["advanced"] for job in resumed["progress"]):
            print(json.dumps(resumed), flush=True)
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Scan counters are preserved but forward progress is not yet confirmed"
            )
        time.sleep(10)
    run(
        "docker",
        "cp",
        "librephotos-app:" + temporary_root + "/after.json",
        str(checkpoint / "after.json"),
    )
    (checkpoint / "after.json").chmod(0o600)
    record = {
        "image": image,
        "previous_image": previous_image,
        "deployed_at": stamp,
        "checkpoint": str(checkpoint),
        "scan_progress_preserved": True,
        "database_container_preserved": True,
    }
    (root / "deployment.json").write_text(json.dumps(record, indent=2) + "\n")
    (checkpoint / "receipt.json").write_text(json.dumps(record, indent=2) + "\n")
    phase("Deployment complete; scan progress preserved and forward progress verified")
    print(json.dumps(record), flush=True)
except BaseException:
    phase("Deployment did not complete. Recovery checkpoint: " + str(checkpoint))
    if not checkpointed and env_path.read_text() == previous:
        phase("The original schema and image are retained")
        if inspect("librephotos-app", "{{.State.Running}}") == "true":
            cluster_probe = subprocess.run(
                [
                    "docker",
                    "exec",
                    "librephotos-app",
                    "python",
                    "-c",
                    'import runpy; m=runpy.run_path("/tmp/librephotos-scan-checkpoint.py"); raise SystemExit(0 if m["clusters"]() else 3)',
                ]
            )
            if cluster_probe.returncode == 3:
                phase(
                    "The queue is drained; recreating the original application to resume it"
                )
                run(
                    "docker",
                    "compose",
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    "app",
                )
            else:
                phase(
                    "The existing queue cluster is retained; inspect it before another deployment"
                )
        else:
            run("docker", "compose", "up", "-d", "--no-deps", "app")
    else:
        phase(
            "Keep the matching schema and image together. Restore the checkpoint database and private environment before rolling back."
        )
    raise
