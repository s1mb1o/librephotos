"""Install one immutable LAN image. Keep state and backups outside the image."""

import datetime
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path("/srv/librephotos")
image = sys.argv[1]
if not image.startswith("registry.my.3simbio.ru/librephotos/app:"):
    raise SystemExit("Unexpected image repository")
lock = (root / ".deploy.lock").open("w")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
env_path = root / ".env"
previous = env_path.read_text()
values = dict(line.split("=", 1) for line in previous.splitlines() if line and not line.startswith("#"))
photo_root = Path(values["LP_PHOTO_ROOT"])
if not (photo_root / "Years").is_dir():
    raise SystemExit("PhotoLibrary is unavailable. Refusing deployment.")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, cwd=root, **kwargs)


run("docker", "pull", image)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backups = root / "backups"
backups.mkdir(mode=0o700, exist_ok=True)
running = subprocess.run(
    ["docker", "inspect", "--format", "{{.State.Running}}", "librephotos-db"],
    capture_output=True, text=True, check=False,
)
if running.returncode == 0 and running.stdout.strip() == "true":
    backup = backups / f"before-{stamp}.dump"
    with backup.open("xb") as stream:
        os.chmod(backup, 0o600)
        run("docker", "exec", "librephotos-db", "pg_dump", "-U", "librephotos", "-d", "librephotos", "-Fc", stdout=stream)
    print(f"Database backup: {backup}", flush=True)
previous_image = next((line[9:] for line in previous.splitlines() if line.startswith("LP_IMAGE=")), None)
snapshot = backups / f"before-{stamp}.env"
snapshot.write_text(previous)
os.chmod(snapshot, 0o600)
lines = [line for line in previous.splitlines() if not line.startswith("LP_IMAGE=")]
temporary = root / ".env.next"
temporary.write_text("\n".join([*lines, f"LP_IMAGE={image}"]) + "\n")
os.chmod(temporary, 0o600)
temporary.replace(env_path)
run("docker", "compose", "config", "--quiet")
try:
    run("docker", "compose", "up", "-d", "--wait", "--wait-timeout", "600")
except subprocess.CalledProcessError:
    print("Deployment failed. Inspect logs. Restore the database backup before reverting code if migrations ran.", file=sys.stderr)
    raise
# Bootstrap only a missing admin. Rebuilds must preserve a changed password.
username = values.get("LP_ADMIN_USER", "ashmelev")
probe = subprocess.check_output([
    "docker", "exec", "librephotos-app", "python", "manage.py", "shell", "-c",
    "from api.models import User; print('ADMIN_EXISTS=' + str(int(User.objects.filter(username=" + repr(username) + ").exists())))",
], text=True)
if "ADMIN_EXISTS=0" in probe.splitlines():
    bootstrap_env = dict(os.environ)
    bootstrap_env["ADMIN_PASSWORD"] = values["LP_ADMIN_PASSWORD"]
    run("docker", "exec", "-e", "ADMIN_PASSWORD", "librephotos-app", "python", "manage.py", "createadmin", username, values.get("LP_ADMIN_EMAIL", ""), env=bootstrap_env)
record = {"image": image, "previous_image": previous_image, "deployed_at": stamp}
(root / "deployment.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record), flush=True)
