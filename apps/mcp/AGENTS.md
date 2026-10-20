# LibrePhotos MCP adapter

Read the [root instructions](../../AGENTS.md).
Use the official MCP SDK. Keep this service independent of Django and the database.
Use REST for every operation. Do not mount original photos.
Keep transport authentication separate from LibrePhotos API-key authentication.
Use bounded requests, bounded response bodies, and validated response models.
Do not log credentials, upstream response bodies, captions, or filesystem paths.
Send diagnostics to stderr. Reserve stdout for the stdio protocol.
Run `python -m unittest discover -s tests`, `ruff check .`, and `mypy src`.
