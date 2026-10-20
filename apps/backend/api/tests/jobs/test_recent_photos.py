"""A caption job keeps a bounded, private result window across progress updates."""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.accounts.api_keys import create_api_key
from api.classification.captioning import CaptionError
from api.directory_watcher.processing_jobs import generate_caption_job
from api.models import LongRunningJob
from api.models.long_running_job import RECENT_CAPTION_LIMIT
from api.tests.utils import create_test_job, create_test_photo, create_test_user


class RecentJobPhotosTest(TestCase):
    def setUp(self) -> None:
        self.user = create_test_user()
        self.photo = create_test_photo(owner=self.user)
        self.job = create_test_job(
            self.user,
            job_type=LongRunningJob.JOB_GENERATE_CAPTIONS,
            started_at=timezone.now(),
            progress_target=100,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/jobs/{self.job.pk}/recent-photos/"

    def test_bounded_newest_first_window_and_retry_replacement(self) -> None:
        photos = [create_test_photo(owner=self.user) for _ in range(25)]
        for index, photo in enumerate(photos):
            self.job.record_recent_photo(photo, "success", f"Caption {index}")
        self.job.refresh_from_db()
        self.assertEqual(len(self.job.recent_photos), 20)
        self.assertEqual(self.job.recent_photos[0]["photo_id"], str(photos[-1].pk))
        self.assertEqual(self.job.recent_photos[-1]["photo_id"], str(photos[5].pk))
        self.job.record_recent_photo(photos[10], "success", "Retry output")
        self.job.refresh_from_db()
        self.assertEqual(len(self.job.recent_photos), 20)
        self.assertEqual(self.job.recent_photos[0]["caption"], "Retry output")
        self.assertEqual(
            sum(
                row["photo_id"] == str(photos[10].pk) for row in self.job.recent_photos
            ),
            1,
        )

    def test_recent_write_keeps_fresh_counters_and_errors_from_other_writes(
        self,
    ) -> None:
        LongRunningJob.objects.filter(pk=self.job.pk).update(
            progress_current=42, result={"error_count": 1, "errors": ["Existing error"]}
        )
        self.assertTrue(self.job.record_recent_photo(self.photo, "success", "Result"))
        self.job.refresh_from_db()
        self.assertEqual(self.job.progress_current, 42)
        self.assertEqual(
            self.job.result, {"error_count": 1, "errors": ["Existing error"]}
        )
        self.job.cancel()
        self.assertFalse(
            self.job.record_recent_photo(self.photo, "success", "Too late")
        )
        self.job.refresh_from_db()
        self.assertEqual(self.job.recent_photos[0]["caption"], "Result")
        self.assertTrue(self.job.cancelled)

    def test_finished_job_keeps_history_and_refuses_late_results(self) -> None:
        self.job.record_recent_photo(self.photo, "success", "Original")
        self.job.complete()
        self.assertFalse(self.job.record_recent_photo(self.photo, "failed"))
        response = self.client.get(self.url)
        self.assertTrue(response.data["finished"])
        self.assertEqual(response.data["results"][0]["caption"], "Original")

    def test_caption_bound_and_cross_owner_write(self) -> None:
        self.job.record_recent_photo(
            self.photo, "success", "x" * (RECENT_CAPTION_LIMIT + 1)
        )
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data["results"][0]["caption"]), RECENT_CAPTION_LIMIT
        )
        self.assertTrue(response.data["results"][0]["truncated"])
        self.assertFalse(
            self.job.record_recent_photo(
                create_test_photo(owner=create_test_user()), "success", "Foreign"
            )
        )

    def test_success_error_and_disabled_processing_are_recorded_with_progress(
        self,
    ) -> None:
        with (
            patch(
                "api.directory_watcher.processing_jobs.captioning.captioning_available",
                return_value=True,
            ),
            patch(
                "api.directory_watcher.processing_jobs.captioning.caption_photo",
                return_value="A person wears a hat.",
            ),
        ):
            generate_caption_job(self.photo.pk, str(self.job.job_id))
        self.job.refresh_from_db()
        self.assertEqual(self.job.recent_photos[0]["caption"], "A person wears a hat.")
        self.assertEqual(self.job.recent_photos[0]["status"], "success")
        self.assertEqual(self.job.progress_current, 1)
        with (
            patch(
                "api.directory_watcher.processing_jobs.captioning.captioning_available",
                return_value=True,
            ),
            patch(
                "api.directory_watcher.processing_jobs.captioning.caption_photo",
                side_effect=CaptionError("Provider unavailable"),
            ),
        ):
            generate_caption_job(self.photo.pk, str(self.job.job_id))
        self.job.refresh_from_db()
        self.assertEqual(self.job.recent_photos[0]["status"], "failed")
        self.assertEqual(self.job.recent_photos[0]["caption"], "")
        self.assertEqual(self.job.result["error_count"], 1)
        with patch(
            "api.directory_watcher.processing_jobs.captioning.captioning_available",
            return_value=False,
        ):
            generate_caption_job(self.photo.pk, str(self.job.job_id))
        self.job.refresh_from_db()
        self.assertEqual(self.job.recent_photos[0]["status"], "skipped")
        self.assertEqual(self.job.progress_current, 3)

    def test_cancel_during_inference_does_not_publish_a_late_result(self) -> None:
        def respond(*args: object, **kwargs: object) -> str:
            self.job.cancel()
            return "Late caption"

        with (
            patch(
                "api.directory_watcher.processing_jobs.captioning.captioning_available",
                return_value=True,
            ),
            patch(
                "api.directory_watcher.processing_jobs.captioning.caption_photo",
                side_effect=respond,
            ),
        ):
            generate_caption_job(self.photo.pk, str(self.job.job_id))
        self.job.refresh_from_db()
        self.assertTrue(self.job.cancelled)
        self.assertEqual(self.job.recent_photos, [])
        self.assertEqual(self.job.result, {"status": "cancelled"})

    def test_missing_removed_trashed_and_transferred_photos_are_filtered(self) -> None:
        self.job.record_recent_photo(self.photo, "success", "Private snapshot")
        self.assertEqual(len(self.client.get(self.url).data["results"]), 1)
        for fields in (
            {"removed": True},
            {"removed": False, "in_trashcan": True},
            {"in_trashcan": False, "owner": create_test_user()},
        ):
            for name, value in fields.items():
                setattr(self.photo, name, value)
            self.photo.save(update_fields=list(fields))
            self.assertEqual(self.client.get(self.url).data["results"], [])
        self.photo.delete()
        self.assertEqual(self.client.get(self.url).data["results"], [])

    def test_anonymous_and_api_keys_cannot_read_feed_or_private_job_field(self) -> None:
        self.job.record_recent_photo(self.photo, "success", "Private snapshot")
        response = self.client.get(f"/api/jobs/{self.job.pk}/")
        self.assertNotIn("recent_photos", response.data)
        self.assertNotIn("Private snapshot", str(response.data))
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
        _, secret = create_api_key(self.user, "jobs only", permissions=["jobs:read"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {secret}")
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_response_uses_two_queries_for_two_or_eight_photos(self) -> None:
        for count in (2, 8):
            for _ in range(count):
                self.job.record_recent_photo(
                    create_test_photo(owner=self.user), "success", "Caption"
                )
            with self.assertNumQueries(2):
                response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["limit"], 20)

    def test_last_result_is_returned_with_the_completion_flag(self) -> None:
        self.job.update_progress(current=0, target=1)
        with (
            patch(
                "api.directory_watcher.processing_jobs.captioning.captioning_available",
                return_value=True,
            ),
            patch(
                "api.directory_watcher.processing_jobs.captioning.caption_photo",
                return_value="Final caption",
            ),
        ):
            generate_caption_job(self.photo.pk, str(self.job.job_id))
        response = self.client.get(self.url)
        self.assertTrue(response.data["finished"])
        self.assertEqual(response.data["results"][0]["caption"], "Final caption")

    def test_stale_worker_instances_merge_each_others_results(self) -> None:
        other = LongRunningJob.objects.get(pk=self.job.pk)
        self.job.record_recent_photo(self.photo, "success", "First")
        other.record_recent_photo(
            create_test_photo(owner=self.user), "success", "Second"
        )
        self.job.refresh_from_db()
        self.assertEqual(
            [row["caption"] for row in self.job.recent_photos], ["Second", "First"]
        )
