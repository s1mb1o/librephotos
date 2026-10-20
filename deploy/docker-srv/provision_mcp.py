"""Provision separate persistent MCP and scoped account credentials on docker-srv."""

import hashlib
import json
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path("/srv/librephotos/mcp")
CREDENTIALS = ROOT / "credentials"
ACCESS = ROOT / "access"
FILES = (
    CREDENTIALS / "principals.json",
    CREDENTIALS / "tokens.json",
    ACCESS / "client-token.private",
)


def write_private(path: Path, data: str, uid: int = 0) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(data)
    os.chown(path, uid, uid)


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run credential provisioning as root on docker-srv.")
    if all(path.is_file() for path in FILES):
        print("Existing MCP credentials retained.")
        return
    if any(path.exists() for path in FILES):
        raise SystemExit("Incomplete MCP credentials exist. Refusing replacement.")
    CREDENTIALS.mkdir(parents=True, mode=0o700, exist_ok=True)
    ACCESS.mkdir(mode=0o700, exist_ok=True)
    CREDENTIALS.chmod(0o700)
    ACCESS.chmod(0o700)
    os.chown(CREDENTIALS, 10001, 10001)
    command = (
        "import json; from api.accounts.api_keys import create_api_key; from api.models import User; "
        "user=User.objects.get(username='ashmelev',is_active=True); "
        "key,secret=create_api_key(user,'MCP docker-srv read-only'); "
        "print(json.dumps({'id':str(key.id),'api_key':secret,'owner_id':user.pk}))"
    )
    output = subprocess.check_output(
        [
            "docker",
            "exec",
            "librephotos-app",
            "python",
            "manage.py",
            "shell",
            "-c",
            command,
        ],
        text=True,
    )
    account = json.loads(output.strip().splitlines()[-1])
    token = "lpmcp_" + secrets.token_urlsafe(32)
    subject = "ashmelev"
    digest = hashlib.sha256(token.encode()).hexdigest()
    write_private(FILES[0], json.dumps({subject: account["api_key"]}) + "\n", 10001)
    write_private(FILES[1], json.dumps({digest: subject}) + "\n", 10001)
    write_private(FILES[2], token + "\n")
    (ROOT / "provision.json").write_text(
        json.dumps(
            {
                "subject": subject,
                "api_key_id": account["id"],
                "owner_id": account["owner_id"],
                "permissions": ["photos:read", "jobs:read"],
            },
            indent=2,
        )
        + "\n"
    )
    print("Created a read-only account key and a separate persistent MCP token.")
    print("Client token: /srv/librephotos/mcp/access/client-token.private (root only).")


if __name__ == "__main__":
    main()
