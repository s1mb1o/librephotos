"""Face grounding, confidence gates, safe updates and inference races."""

import datetime
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

import PIL.Image
from constance.test import override_config
from django.test import TestCase, override_settings

from api.classification.captioning import CaptionError, caption_photo
from api.classification.identity_context import (
    identity_context,
    trusted_identity,
)
from api.classification.identity_updates import (
    invalidate_identity_captions,
    refresh_identity_caption,
)
from api.directory_watcher.processing_jobs import photos_to_caption
from api.faces.classify import persist_face_predictions
from api.faces.labels import relabel_faces
from api.models import Face, Photo, PhotoCaption, PhotoSearch
from api.models.photo_caption import CAPTION_IDENTITY_KEY as IDENTITY_KEY
from api.models.photo_caption import display_captions
from api.sharing.grants import LibraryGrant, shown_captions
from api.sharing.library_search import term_q
from api.tests.utils import (
    create_test_face,
    create_test_person,
    create_test_photo,
    create_test_user,
)


@override_config(CAPTIONING_MODEL="lfm2_vl_450m", IMAGE_CAPTIONING_ENABLED=True)
@override_settings(FEATURE_IMAGE_CAPTIONING=True)
class IdentityCaptionTest(TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=directory.name))
        self.path = Path(directory.name) / "photo.jpg"
        with PIL.Image.new("RGB", (240, 120), "white") as image:
            image.save(self.path)
        self.user = create_test_user()
        self.photo = create_test_photo(
            owner=self.user,
            thumbnail_big=self.path.name,
            captions_json={"user_caption": "My own caption"},
        )
        self.alex = create_test_person(name="Alexander", cluster_owner=self.user)
        self.bob = create_test_person(name="Boris", cluster_owner=self.user)
        self.face = create_test_face(
            photo=self.photo,
            location_left=10,
            location_top=10,
            location_right=70,
            location_bottom=100,
        )

    def saved(self) -> dict:
        return PhotoCaption.objects.get(pk=self.photo.pk).captions_json

    def generate(self) -> str:
        with patch(
            "api.classification.captioning.generate_caption",
            return_value=f"[[face:{self.face.pk}]] is wearing a hat.",
        ):
            return caption_photo(self.photo.caption_instance)

    def test_initial_anonymous_caption_becomes_named_without_another_vlm_call(
        self,
    ) -> None:
        self.assertEqual(self.generate(), "A person is wearing a hat.")
        with (
            patch("api.classification.identity_updates.enqueue_task") as queue,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.face.person = self.alex
            self.face.save(update_fields=["person"])
        self.assertEqual(self.saved()["im2txt"], "Alexander is wearing a hat.")
        self.assertEqual(self.saved()["user_caption"], "My own caption")
        queue.assert_not_called()
        self.assertIn(
            "Alexander", PhotoSearch.objects.get(pk=self.photo.pk).search_captions
        )

    def test_confirmed_name_rename_correction_undo_and_deletion_rebind_safely(
        self,
    ) -> None:
        self.face.person = self.alex
        self.face.save(update_fields=["person"])
        self.generate()
        with self.captureOnCommitCallbacks(execute=True):
            self.alex.name = "Sasha"
            self.alex.save(update_fields=["name"])
        self.assertEqual(self.saved()["im2txt"], "Sasha is wearing a hat.")
        with self.captureOnCommitCallbacks(execute=True):
            relabel_faces(self.user, Face.objects.filter(pk=self.face.pk), self.bob)
        self.assertEqual(self.saved()["im2txt"], "Boris is wearing a hat.")
        with self.captureOnCommitCallbacks(execute=True):
            relabel_faces(self.user, Face.objects.filter(pk=self.face.pk), self.alex)
        self.assertEqual(self.saved()["im2txt"], "Sasha is wearing a hat.")
        with self.captureOnCommitCallbacks(execute=True):
            self.alex.delete()
        self.assertEqual(self.saved()["im2txt"], "A person is wearing a hat.")

    def test_only_agreeing_strong_predictions_insert_a_name_and_confidence_loss_removes_it(
        self,
    ) -> None:
        self.face.classification_person = self.alex
        self.face.cluster_person = self.alex
        self.face.classification_probability = 0.995
        self.face.cluster_probability = 0.995
        self.face.save()
        self.assertEqual(self.generate(), "Alexander is wearing a hat.")
        with self.captureOnCommitCallbacks(execute=True):
            self.face.classification_probability = 0.98
            self.face.save(update_fields=["classification_probability"])
        self.assertEqual(self.saved()["im2txt"], "A person is wearing a hat.")
        self.face.classification_probability = float("nan")
        self.assertIsNone(trusted_identity(self.face, self.photo, 0.99))
        self.face.classification_probability = float("inf")
        self.assertIsNone(trusted_identity(self.face, self.photo, 0.99))

    def test_conflicting_predictions_unknown_people_and_other_owners_are_anonymous(
        self,
    ) -> None:
        self.face.classification_person = self.alex
        self.face.cluster_person = self.bob
        self.face.classification_probability = 1
        self.face.cluster_probability = 1
        self.face.save()
        self.assertEqual(self.generate(), "A person is wearing a hat.")
        for person in (
            create_test_person(kind="UNKNOWN", cluster_owner=self.user),
            create_test_person(cluster_owner=create_test_user()),
        ):
            self.face.person = person
            self.face.save()
            self.assertEqual(self.generate(), "A person is wearing a hat.")

    def test_rejected_identity_and_naming_opt_out_remove_names(self) -> None:
        self.face.person = self.alex
        self.face.save()
        self.generate()
        with self.captureOnCommitCallbacks(execute=True):
            self.face.rejected_persons.add(self.alex)
        self.assertEqual(self.saved()["im2txt"], "A person is wearing a hat.")
        with self.captureOnCommitCallbacks(execute=True):
            self.face.rejected_persons.clear()
        self.assertEqual(self.saved()["im2txt"], "Alexander is wearing a hat.")
        with (
            patch("api.classification.identity_updates.enqueue_task"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.user.llm_settings = {
                "enabled": True,
                "add_person": False,
                "add_location": True,
            }
            self.user.save(update_fields=["llm_settings"])
        self.assertNotIn("Alexander", self.saved()["im2txt"])

    def test_vlm_receives_boxes_and_tokens_without_names_and_original_is_unchanged(
        self,
    ) -> None:
        self.face.person = self.alex
        self.face.save()
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        paths = []

        def respond(*, image_path: str, prompt: str) -> str:
            paths.append(image_path)
            with PIL.Image.open(image_path) as image:
                self.assertEqual(image.size, (240, 120))
            self.assertIn("[10, 10, 70, 100]", prompt)
            self.assertIn(f"[[face:{self.face.pk}]]", prompt)
            self.assertNotIn("Alexander", prompt)
            return f"[[face:{self.face.pk}]] is wearing a hat."

        with patch(
            "api.classification.captioning.generate_caption", side_effect=respond
        ):
            self.assertEqual(
                caption_photo(self.photo.caption_instance),
                "Alexander is wearing a hat.",
            )
        self.assertTrue(paths)
        self.assertFalse(Path(paths[0]).exists())
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), digest)

    def test_multiple_people_are_bound_to_their_own_boxes(self) -> None:
        self.face.person = self.alex
        self.face.save()
        other = create_test_face(
            photo=self.photo,
            person=self.bob,
            location_left=120,
            location_top=10,
            location_right=180,
            location_bottom=100,
        )
        with patch(
            "api.classification.captioning.generate_caption",
            return_value=f"[[face:{self.face.pk}]] wears a hat beside [[face:{other.pk}]].",
        ):
            self.assertEqual(
                caption_photo(self.photo.caption_instance),
                "Alexander wears a hat beside Boris.",
            )

    def test_invalid_and_later_frame_boxes_never_introduce_names(self) -> None:
        self.face.person = self.alex
        for changes in (
            {"location_right": 1000},
            {"location_right": 70, "video_time": 2.0},
            {"video_time": None, "deleted": True},
        ):
            for key, value in changes.items():
                setattr(self.face, key, value)
            self.face.save()
            self.assertEqual(self.generate(), "A person is wearing a hat.")

    def test_face_geometry_change_anonymizes_and_queues_one_refresh(self) -> None:
        self.face.person = self.alex
        self.face.save()
        self.generate()
        with (
            patch("api.classification.identity_updates.enqueue_task") as queue,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.face.location_left = 15
            self.face.save(update_fields=["location_left"])
            invalidate_identity_captions((self.photo.pk,))
        self.assertNotIn("Alexander", self.saved()["im2txt"])
        self.assertTrue(self.saved()[IDENTITY_KEY]["stale"])
        self.assertEqual(queue.call_count, 1)
        self.assertIn(self.photo, photos_to_caption(self.user, False))

    def test_superseded_refresh_and_provider_failure_preserve_manual_text(self) -> None:
        self.generate()
        with (
            patch("api.classification.identity_updates.enqueue_task"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.face.location_left = 15
            self.face.save(update_fields=["location_left"])
        pending = self.saved()[IDENTITY_KEY]["pending_key"]
        with patch("api.classification.captioning.caption_photo") as generate:
            refresh_identity_caption(self.photo.pk, self.user.pk, "old-key")
        generate.assert_not_called()
        with patch(
            "api.classification.captioning.caption_photo",
            side_effect=CaptionError("Provider unavailable"),
        ):
            with self.assertRaises(CaptionError):
                refresh_identity_caption(self.photo.pk, self.user.pk, pending)
        self.assertEqual(self.saved()["user_caption"], "My own caption")
        self.assertTrue(self.saved()[IDENTITY_KEY]["stale"])
        self.assertIsNone(self.saved()[IDENTITY_KEY]["pending_key"])

    def test_inflight_identity_change_cannot_publish_an_old_name(self) -> None:
        self.face.person = self.alex
        self.face.save()

        def respond(*, image_path: str, prompt: str) -> str:
            self.face.person = self.bob
            self.face.save(update_fields=["person"])
            return f"[[face:{self.face.pk}]] is wearing a hat."

        with patch(
            "api.classification.captioning.generate_caption", side_effect=respond
        ):
            with self.assertRaises(CaptionError):
                caption_photo(self.photo.caption_instance)
        self.assertNotIn("im2txt", self.saved())

    def test_manual_caption_edited_during_inference_is_preserved(self) -> None:
        def respond(*, image_path: str, prompt: str) -> str:
            PhotoCaption.objects.filter(pk=self.photo.pk).update(
                captions_json={"user_caption": "Edited while waiting", "custom": "keep"}
            )
            return "A person wearing a hat."

        with patch(
            "api.classification.captioning.generate_caption", side_effect=respond
        ):
            caption_photo(self.photo.caption_instance)
        self.assertEqual(self.saved()["user_caption"], "Edited while waiting")
        self.assertEqual(self.saved()["custom"], "keep")

    def test_identity_context_reads_current_settings_not_cached_owner(self) -> None:
        self.face.person = self.alex
        self.face.save()
        self.assertTrue(identity_context(self.photo).identities)
        self.user.llm_settings = {"enabled": False}
        self.user.save(update_fields=["llm_settings"])
        self.assertFalse(identity_context(self.photo).identities)

    def test_internal_face_evidence_is_not_returned_or_searchable(self) -> None:
        self.generate()
        data = self.saved()
        data[IDENTITY_KEY]["private_evidence"] = "privateidentitymarker47"
        PhotoCaption.objects.filter(pk=self.photo.pk).update(captions_json=data)
        self.assertNotIn(IDENTITY_KEY, display_captions(data))
        grant = LibraryGrant(captions=True, people=True, location=True)
        shown = shown_captions(data, grant)
        self.assertIsInstance(shown, dict)
        self.assertNotIn(IDENTITY_KEY, shown)
        self.assertFalse(
            Photo.objects.filter(pk=self.photo.pk)
            .filter(term_q("privateidentitymarker47", grant))
            .exists()
        )

    def test_generated_names_cannot_be_searched_through_a_share_that_hides_people(
        self,
    ) -> None:
        self.face.person = self.alex
        self.face.save()
        self.generate()
        self.assertFalse(
            Photo.objects.filter(pk=self.photo.pk)
            .filter(term_q("Alexander", LibraryGrant(captions=True)))
            .exists()
        )

    def test_bulk_prediction_updates_refresh_an_existing_anonymous_caption(
        self,
    ) -> None:
        self.generate()
        self.face.classification_person = self.alex
        self.face.cluster_person = self.alex
        self.face.classification_probability = 0.995
        self.face.cluster_probability = 0.995
        with (
            patch("api.classification.identity_updates.enqueue_task") as queue,
            self.captureOnCommitCallbacks(execute=True),
        ):
            persist_face_predictions([self.face])
        self.assertEqual(self.saved()["im2txt"], "Alexander is wearing a hat.")
        queue.assert_not_called()

    def test_legacy_caption_gets_a_fresh_grounded_pass(self) -> None:
        PhotoCaption.objects.filter(pk=self.photo.pk).update(
            captions_json={
                "im2txt": "A person is wearing a hat.",
                "user_caption": "Manual",
            }
        )
        with (
            patch("api.classification.identity_updates.enqueue_task") as queue,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.face.person = self.alex
            self.face.save(update_fields=["person"])
        self.assertEqual(queue.call_count, 1, self.saved())
        key = self.saved()[IDENTITY_KEY]["pending_key"]
        with patch(
            "api.classification.captioning.generate_caption",
            return_value=f"[[face:{self.face.pk}]] is wearing a hat.",
        ):
            refresh_identity_caption(self.photo.pk, self.user.pk, key)
        self.assertEqual(self.saved()["im2txt"], "Alexander is wearing a hat.")
        self.assertEqual(self.saved()["user_caption"], "Manual")
        self.assertFalse(self.saved()[IDENTITY_KEY]["stale"])

    def test_inferred_identity_respects_encoding_unmatched_dates_and_user_threshold(
        self,
    ) -> None:
        self.face.classification_person = self.alex
        self.face.cluster_person = self.alex
        self.face.classification_probability = 0.995
        self.face.cluster_probability = 0.995
        self.assertIsNotNone(trusted_identity(self.face, self.photo, 0.99))
        self.assertIsNone(trusted_identity(self.face, self.photo, 0.999))
        original_encoding = self.face.encoding
        self.face.encoding = None
        self.assertIsNone(trusted_identity(self.face, self.photo, 0.99))
        self.face.encoding = original_encoding
        self.face.unmatched_by = "test"
        self.assertIsNone(trusted_identity(self.face, self.photo, 0.99))
        self.face.unmatched_by = ""
        self.alex.birth_date = datetime.date(2020, 1, 1)
        self.photo.exif_timestamp = datetime.datetime(2019, 1, 1, tzinfo=datetime.UTC)
        self.assertIsNone(trusted_identity(self.face, self.photo, 0.99))
        self.user.confidence_person = 0.999
        self.user.save(update_fields=["confidence_person"])
        self.face.save()
        self.assertFalse(identity_context(self.photo).identities)

    def test_overlapping_faces_and_duplicate_inferred_people_are_anonymous(
        self,
    ) -> None:
        self.face.classification_person = self.alex
        self.face.cluster_person = self.alex
        self.face.classification_probability = 0.995
        self.face.cluster_probability = 0.995
        self.face.save()
        other = create_test_face(
            photo=self.photo,
            classification_person=self.alex,
            cluster_person=self.alex,
            classification_probability=0.995,
            cluster_probability=0.995,
            location_left=120,
            location_top=10,
            location_right=180,
            location_bottom=100,
        )
        self.assertEqual(len(identity_context(self.photo).anchors), 2)
        self.assertFalse(identity_context(self.photo).identities)
        other.location_left = 10
        other.location_right = 70
        other.save(update_fields=["location_left", "location_right"])
        self.assertFalse(identity_context(self.photo).anchors)
        self.assertFalse(identity_context(self.photo).identities)

    def test_unknown_tokens_are_anonymous_even_when_the_number_names_another_face(
        self,
    ) -> None:
        other = create_test_face(
            photo=create_test_photo(owner=self.user), person=self.alex
        )
        with patch(
            "api.classification.captioning.generate_caption",
            return_value=f"[[face:{other.pk}]] is wearing a hat.",
        ):
            self.assertEqual(
                caption_photo(self.photo.caption_instance), "A person is wearing a hat."
            )
