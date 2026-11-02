"""Configuration and protected credential loading. Values are never logged."""

import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


def protected_file(path: str) -> str:
    target = Path(path)
    if not stat.S_ISREG(target.stat().st_mode) or target.stat().st_mode & 0o077:
        raise ValueError("Credential files must be regular files accessible only to their owner.")
    if target.stat().st_size > 65536:
        raise ValueError("Credential file is too large.")
    return target.read_text().strip()


def checked_url(value: str, *, https: bool = False) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ({"https"} if https else {"http", "https"})
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Configure an absolute service URL without credentials, query, or fragment."
        )
    return value


def token_subjects(path: str, principals: dict[str, str]) -> dict[str, str]:
    """Load token verifiers on every request so removal revokes access immediately."""
    raw: object = json.loads(protected_file(path))
    if (
        not isinstance(raw, dict)
        or not raw
        or not all(
            isinstance(digest, str)
            and re.fullmatch(r"[a-f0-9]{64}", digest)
            and isinstance(subject, str)
            and subject in principals
            for digest, subject in raw.items()
        )
    ):
        raise ValueError("Configure SHA-256 MCP token verifiers mapped to known subjects.")
    return {str(digest): str(subject) for digest, subject in raw.items()}


@dataclass(frozen=True, repr=False)
class Config:
    base_url: str
    api_key: str = field(default="", repr=False)
    transport: str = "stdio"
    enable_writes: bool = False
    issuer: str = ""
    jwks_url: str = ""
    resource_url: str = ""
    principals: dict[str, str] = field(default_factory=dict, repr=False)
    auth_mode: str = "oauth"
    tokens_file: str = ""

    @classmethod
    def from_environment(cls, transport: str) -> "Config":
        base = checked_url(os.environ.get("LIBREPHOTOS_URL", "http://librephotos:3000"))
        writes = os.environ.get("LIBREPHOTOS_MCP_ENABLE_WRITES", "false").lower()
        if writes not in {"true", "false"}:
            raise ValueError("LIBREPHOTOS_MCP_ENABLE_WRITES must be true or false.")
        if transport == "stdio":
            path = os.environ.get("LIBREPHOTOS_API_KEY_FILE", "")
            key = protected_file(path) if path else os.environ.get("LIBREPHOTOS_API_KEY", "")
            if not key.startswith("lp_"):
                raise ValueError("Configure a LibrePhotos API key for stdio.")
            return cls(base, key, transport, writes == "true")
        mode = os.environ.get("LIBREPHOTOS_MCP_AUTH_MODE", "oauth")
        if mode not in {"oauth", "token"}:
            raise ValueError("LIBREPHOTOS_MCP_AUTH_MODE must be oauth or token.")
        issuer = (
            checked_url(os.environ.get("LIBREPHOTOS_MCP_ISSUER", ""), https=True)
            if mode == "oauth"
            else ""
        )
        jwks = (
            checked_url(os.environ.get("LIBREPHOTOS_MCP_JWKS_URL", ""), https=True)
            if mode == "oauth"
            else ""
        )
        resource = checked_url(
            os.environ.get("LIBREPHOTOS_MCP_RESOURCE_URL", ""), https=mode == "oauth"
        )
        raw: object = json.loads(
            protected_file(os.environ.get("LIBREPHOTOS_MCP_PRINCIPALS_FILE", ""))
        )
        if (
            not isinstance(raw, dict)
            or not raw
            or not all(
                isinstance(subject, str)
                and bool(subject)
                and isinstance(key, str)
                and key.startswith("lp_")
                for subject, key in raw.items()
            )
        ):
            raise ValueError("Configure a subject-to-LibrePhotos-key mapping.")
        principals: dict[str, str] = {str(subject): str(key) for subject, key in raw.items()}
        if len(set(principals.values())) != len(principals):
            raise ValueError("Each MCP subject requires a separate LibrePhotos API key.")
        tokens_file = os.environ.get("LIBREPHOTOS_MCP_TOKENS_FILE", "") if mode == "token" else ""
        if mode == "token":
            token_subjects(tokens_file, principals)
        return cls(
            base,
            transport=transport,
            enable_writes=writes == "true",
            issuer=issuer,
            jwks_url=jwks,
            resource_url=resource,
            principals=principals,
            auth_mode=mode,
            tokens_file=tokens_file,
        )
