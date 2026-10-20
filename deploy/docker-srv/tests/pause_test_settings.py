from librephotos.settings.test_sqlite import *

DEBUG = False
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/tmp/pause-test.sqlite3",
        "OPTIONS": {"timeout": 30, "transaction_mode": "IMMEDIATE"},
    }
}
Q_CLUSTER = {
    **Q_CLUSTER,
    "workers": 1,
    "recycle": 2,
    "max_rss": 0,
    "queue_limit": 6,
    "guard_cycle": 0.2,
    "testing": False,
}

from librephotos.logging_bootstrap import build_logging_config

LOGGING = build_logging_config(
    logs_root=LOGS_ROOT, level="INFO", to_console=True, logger_levels={}
)
