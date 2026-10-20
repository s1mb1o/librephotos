"""Remote vector validation, resumable conversion, and isolated index persistence."""

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import requests
from constance.test import override_config
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import LongRunningJob, PhotoEmbedding
from api.runtime.model_settings import save_remote_config
from api.runtime.remote_inference import RemoteInferenceError
from api.search.embedding_jobs import batch_calculate_clip_embedding
from api.search.profiles import EmbeddingProfile, active_profile, selected_profile
from api.search.remote_embeddings import remote_embeddings
from api.search.semantic import OPENCLIP, SIGLIP2
from api.tests.stubs import load_backend_file
from api.tests.utils import create_test_job, create_test_photo, create_test_user
from image_similarity import retrieval_index
from image_similarity.retrieval_index import IndexBuildError, RetrievalIndex


def vector(dimension: int = 1152, axis: int = 0) -> list[float]:
    values = [0.0] * dimension
    values[axis] = 1.0
    return values


def response(body: object) -> requests.Response:
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps(body).encode()
    return result


class RemoteEmbeddingClientTest(TestCase):
    def setUp(self) -> None:
        self.profile = EmbeddingProfile(
            SIGLIP2,
            "http://embed.example/v1",
            "siglip2-so400m-patch16-naflex",
            token="token",
        )

    @patch("api.runtime.remote_inference.requests.post")
    def test_batched_results_are_reordered_and_normalized(self, post) -> None:
        post.return_value = response(
            {
                "model": self.profile.model_name,
                "data": [
                    {"index": 1, "embedding": [value * 3 for value in vector(axis=1)]},
                    {"index": 0, "embedding": [value * 2 for value in vector()]},
                ],
            }
        )
        values = remote_embeddings(self.profile, ["a dog", "a cat"])
        self.assertEqual(values, [vector(), vector(axis=1)])
        body = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(body["input"], ["a dog", "a cat"])
        self.assertEqual(body["max_num_patches"], 256)
        self.assertEqual(body["encoding_format"], "float")

    @patch("api.runtime.remote_inference.requests.post")
    def test_malformed_vectors_and_positions_are_rejected(self, post) -> None:
        invalid = [
            vector(512),
            [0.0] * 1152,
            [float("nan")] * 1152,
            [True] * 1152,
            [float("inf")] * 1152,
        ]
        for values in invalid:
            with self.subTest(first=values[0]):
                post.return_value = response(
                    {
                        "model": self.profile.model_name,
                        "data": [{"index": 0, "embedding": values}],
                    }
                )
                with self.assertRaises(RemoteInferenceError):
                    remote_embeddings(self.profile, ["query"])
        for rows in (
            [{"index": 0, "embedding": vector()}] * 2,
            [{"index": -1, "embedding": vector()}],
            [],
        ):
            post.return_value = response(
                {"model": self.profile.model_name, "data": rows}
            )
            with self.assertRaises(RemoteInferenceError):
                remote_embeddings(self.profile, ["query"])

    @patch("api.runtime.remote_inference.requests.post")
    def test_wrong_model_is_rejected(self, post) -> None:
        post.return_value = response(
            {"model": "another-model", "data": [{"index": 0, "embedding": vector()}]}
        )
        with self.assertRaisesMessage(RemoteInferenceError, "unexpected model"):
            remote_embeddings(self.profile, ["query"])

    @patch("api.search.remote_embeddings._label_vectors")
    @patch("service.tags.openclip.openclip.OpenCLIP._load_tags")
    def test_generated_things_use_cosine_threshold_and_shared_vocabulary(
        self, vocabulary, encoded
    ) -> None:
        import numpy as np

        from api.search.remote_embeddings import labels_for

        vocabulary.return_value = ["dog", "car", "animal"]
        related = vector()
        related[0], related[1] = 0.8, 0.6
        encoded.return_value = np.asarray(
            [vector(), vector(axis=1), related], dtype=np.float32
        )
        save_remote_config("embeddings", {"tag_threshold": 0.9})
        self.assertEqual(labels_for(self.profile, vector()), ["dog"])
        save_remote_config("embeddings", {"tag_threshold": 0.5})
        self.assertEqual(labels_for(self.profile, vector()), ["dog", "animal"])
        self.assertEqual(encoded.call_args.args[1], ("dog", "car", "animal"))

    def test_embedding_identity_includes_processing_but_not_token(self) -> None:
        self.assertEqual(self.profile.key, replace(self.profile, token="rotated").key)
        for changed in (
            replace(self.profile, max_num_patches=1024),
            replace(self.profile, revision="revision-2"),
            replace(self.profile, model_name="other"),
            replace(self.profile, url="http://other.example/v1"),
        ):
            self.assertNotEqual(self.profile.key, changed.key)
        self.assertNotIn("token", self.profile.specification)
        self.assertNotIn("token=", repr(self.profile))


@override_config(EMBEDDING_MODEL=SIGLIP2, SCENE_CLASSIFICATION_ENABLED=False)
class RemoteEmbeddingJobTest(TestCase):
    def setUp(self) -> None:
        self.user = create_test_user()
        save_remote_config(
            "embeddings",
            {
                "url": "http://embed.example/v1",
                "model_name": "siglip2-so400m-patch16-naflex",
            },
        )
        self.photos = [
            create_test_photo(
                owner=self.user,
                clip_embeddings=vector(512),
                clip_embeddings_model=OPENCLIP,
                rating=4,
                captions_json={
                    "user_caption": "Keep this",
                    OPENCLIP: {"tags": ["old"]},
                },
            )
            for _ in range(2)
        ]

    def test_failed_conversion_retains_active_index_and_resumes_completed_batches(
        self,
    ) -> None:
        with (
            patch("api.search.provider_jobs.BATCH_SIZE", 1),
            patch(
                "api.search.provider_jobs.embed_images",
                side_effect=[[vector()], RemoteInferenceError("provider failed")],
            ),
        ):
            with self.assertRaisesMessage(RemoteInferenceError, "provider failed"):
                batch_calculate_clip_embedding(self.user)
        self.assertEqual(PhotoEmbedding.objects.owned_by(self.user).count(), 1)
        self.assertEqual(active_profile(self.user).provider, OPENCLIP)
        with (
            patch(
                "api.search.provider_jobs.embed_images", return_value=[vector()]
            ) as embed,
            patch("api.search.similarity.build_image_similarity_index", return_value=2),
        ):
            batch_calculate_clip_embedding(self.user)
        self.assertEqual(embed.call_count, 1)
        self.assertEqual(len(embed.call_args.args[1]), 1)
        self.assertEqual(active_profile(self.user).key, selected_profile().key)
        self.assertEqual(PhotoEmbedding.objects.owned_by(self.user).count(), 2)
        for photo in self.photos:
            photo.refresh_from_db()
            self.assertEqual(photo.clip_embeddings, vector(512))
            self.assertEqual(photo.rating, 4)
            self.assertEqual(
                photo.caption_instance.captions_json["user_caption"], "Keep this"
            )

    def test_settings_change_mid_build_keeps_one_captured_profile(self) -> None:
        from api.search.provider_jobs import embedding_status

        original = selected_profile()

        def change_settings() -> None:
            save_remote_config(
                "embeddings", {"revision": "checkpoint-2", "max_num_patches": 1024}
            )

        with (
            patch("api.search.provider_jobs.BATCH_SIZE", 1),
            patch(
                "api.search.provider_jobs.embed_images", return_value=[vector()]
            ) as embed,
            patch(
                "api.search.similarity.build_image_similarity_index", return_value=2
            ) as build,
        ):
            batch_calculate_clip_embedding(self.user, heartbeat=change_settings)
        self.assertTrue(
            all(call.args[0].key == original.key for call in embed.call_args_list)
        )
        self.assertEqual(build.call_args.kwargs["profile"].key, original.key)
        self.assertEqual(active_profile(self.user).key, original.key)
        self.assertTrue(embedding_status(self.user)["reindex_required"])

    def test_incomplete_return_to_openclip_preserves_remote_active_index(self) -> None:
        from api.search.profiles import activate_profile
        from api.search.similarity import SimilarityIndexError

        original = selected_profile()
        activate_profile(self.user, original)
        photo = self.photos[0]
        photo.clip_embeddings = None
        photo.save(update_fields=["clip_embeddings"])
        with (
            override_config(EMBEDDING_MODEL=OPENCLIP),
            patch("api.search.embedding_jobs.os.path.exists", return_value=True),
            patch(
                "api.search.embedding_jobs.create_clip_embeddings",
                return_value=([None], [None], None),
            ),
            patch(
                "api.search.embedding_jobs.build_image_similarity_index", return_value=1
            ),
        ):
            with self.assertRaisesMessage(SimilarityIndexError, "still need OpenCLIP"):
                batch_calculate_clip_embedding(self.user)
        self.assertEqual(active_profile(self.user).key, original.key)

    def test_failed_index_commit_does_not_activate_replacement(self) -> None:
        with (
            patch(
                "api.search.provider_jobs.embed_images",
                return_value=[vector(), vector()],
            ),
            patch(
                "api.search.similarity.build_image_similarity_index",
                side_effect=RuntimeError("index unavailable"),
            ),
        ):
            with self.assertRaisesMessage(RuntimeError, "index unavailable"):
                batch_calculate_clip_embedding(self.user)
        self.assertEqual(active_profile(self.user).provider, OPENCLIP)
        self.assertEqual(PhotoEmbedding.objects.owned_by(self.user).count(), 2)
        self.assertTrue(
            LongRunningJob.objects.owned_by(self.user).latest("queued_at").failed
        )

    def test_cancel_keeps_cached_work_without_activating(self) -> None:
        job = create_test_job(self.user, LongRunningJob.JOB_CALCULATE_CLIP_EMBEDDINGS)
        with (
            patch("api.search.provider_jobs.BATCH_SIZE", 1),
            patch("api.search.provider_jobs.embed_images", return_value=[vector()]),
        ):
            batch_calculate_clip_embedding(
                self.user, job_id=job.job_id, heartbeat=job.cancel
            )
        self.assertEqual(PhotoEmbedding.objects.owned_by(self.user).count(), 1)
        self.assertEqual(active_profile(self.user).provider, OPENCLIP)
        job.refresh_from_db()
        self.assertTrue(job.cancelled)

    @override_config(SCENE_CLASSIFICATION_ENABLED=True)
    def test_remote_things_preserve_manual_metadata_and_replace_only_generated_memberships(
        self,
    ) -> None:
        with (
            patch(
                "api.search.provider_jobs.embed_images",
                return_value=[vector(), vector()],
            ),
            patch("api.search.provider_jobs.labels_for", return_value=["dog"]),
            patch("api.search.similarity.build_image_similarity_index", return_value=2),
        ):
            batch_calculate_clip_embedding(self.user)
        for photo in self.photos:
            photo.caption_instance.refresh_from_db()
            values = photo.caption_instance.captions_json
            self.assertEqual(values["user_caption"], "Keep this")
            self.assertEqual(values["tagging_model"], SIGLIP2)
            self.assertEqual(values[SIGLIP2]["tags"], ["dog"])
            self.assertEqual(values[OPENCLIP]["tags"], ["old"])


class ProfileIndexPersistenceTest(TestCase):
    def test_dimensions_and_namespaces_stay_separate_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            local = RetrievalIndex(store_dir=root)
            remote_path = str(Path(root) / "spaces" / ("a" * 64))
            remote = RetrievalIndex(store_dir=remote_path, dimension=1152)
            for index, dimension, image in (
                (local, 512, "local"),
                (remote, 1152, "remote"),
            ):
                index.begin_rebuild(7)
                index.add_to_rebuild(7, [image], [vector(dimension)])
                index.commit_rebuild(7)
            self.assertEqual(local.search_similar(7, vector(512), thres=0.1), ["local"])
            restarted = RetrievalIndex(store_dir=remote_path, dimension=1152)
            self.assertEqual(
                restarted.search_similar(7, vector(), thres=0.1), ["remote"]
            )
            with self.assertRaises(ValueError):
                restarted.search_similar(7, vector(512))
            restarted.begin_rebuild(7)
            with self.assertRaises(IndexBuildError):
                restarted.add_to_rebuild(7, ["wrong"], [vector(512)])
            restarted.abandon_rebuild(7)
            self.assertEqual(
                restarted.search_similar(7, vector(), thres=0.1), ["remote"]
            )

    def test_sidecar_routes_profile_builds_and_deletes_all_user_namespaces(
        self,
    ) -> None:
        main = load_backend_file(
            "image_similarity/main.py",
            name="profile_sidecar_test",
            stubs={"retrieval_index": retrieval_index},
        )
        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(main, "INDEX_ROOT", root),
            patch.object(main, "index", RetrievalIndex(root)),
        ):
            client = main.app.test_client()
            body = {
                "user_id": 7,
                "space": "b" * 64,
                "dimension": 1152,
                "begin": True,
                "commit": True,
                "image_hashes": ["photo"],
                "image_embeddings": [vector()],
            }
            self.assertEqual(client.post("/build/", json=body).status_code, 200)
            self.assertEqual(
                client.post(
                    "/search/",
                    json={
                        "user_id": 7,
                        "space": "b" * 64,
                        "dimension": 1152,
                        "image_embedding": vector(),
                        "threshold": 0.1,
                    },
                ).json["result"],
                ["photo"],
            )
            self.assertEqual(
                client.post(
                    "/build/", json={**body, "space": "../invalid"}
                ).status_code,
                400,
            )
            self.assertEqual(
                client.post("/build/", json={**body, "dimension": 512}).status_code, 400
            )
            self.assertEqual(
                client.delete("/build/", json={"user_id": 7}).status_code, 200
            )
            self.assertFalse((Path(root) / "spaces" / ("b" * 64) / "7.npz").exists())


class SemanticRankingTest(TestCase):
    def test_search_keeps_embedding_order_after_owner_filtering(self) -> None:
        owner = create_test_user(semantic_search_topk=10)
        photos = [create_test_photo(owner=owner) for _ in range(2)]
        victim = create_test_photo(owner=create_test_user())
        hashes = [photos[1].image_hash, victim.image_hash, photos[0].image_hash]
        client = APIClient()
        client.force_authenticate(owner)
        with (
            patch(
                "api.search.filters.calculate_query_embeddings",
                return_value=(vector(512), 1.0),
            ),
            patch("api.search.filters.search_similar_embedding", return_value=hashes),
        ):
            result = client.get("/api/photos/searchlist/?search=dog")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            [row["image_hash"] for row in result.data["results"]],
            [photos[1].image_hash, photos[0].image_hash],
        )
