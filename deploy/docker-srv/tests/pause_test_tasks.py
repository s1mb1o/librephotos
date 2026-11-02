import time

from api.models import LongRunningJob
from django.db.models import F
from django.utils import timezone


def process_group(job_id):
    time.sleep(0.15)
    LongRunningJob.objects.filter(job_id=job_id).update(
        progress_current=F("progress_current") + 1, last_progress_at=timezone.now()
    )
