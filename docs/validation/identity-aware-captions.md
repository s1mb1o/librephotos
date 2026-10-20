# Face-grounded caption validation

Date: 2026-11-02.
Branch: codex/identity-aware-captions.
Base: 4e4b62e45.
Deployment: not performed.
Issue destination: pending the owner's GitLab project URL.

## Environment

Tests ran in a disposable local container.
The source mount was read-only. The container had no network access.
The container used Python 3.14 and the pinned development tools.
Django used the test_sqlite settings and a disposable database.
Images were synthetic. Model responses were mocked.
No private library photos were sent to a provider.
No GPU inference or production catalog changes were performed.

## Automated tests

The caption group passed 114 tests:

```text
api.tests.ml_services.test_identity_captions
api.tests.ml_services.test_image_captioning_client
api.tests.ml_services.test_remote_captioning
api.tests.photos.test_photo_caption_model
api.tests.jobs.test_generate_captions_job
api.tests.photos.test_photo_caption_generation
api.tests.sharing_and_public.test_library_share_search
```

The face regression group passed 135 tests:

```text
api.tests.faces.test_issue_897_label_faces_batch_performance
api.tests.faces.test_delete_labeled_faces
api.tests.faces.test_restore_faces
api.tests.faces.test_person_merge
api.tests.faces.test_person_delete
api.tests.faces.test_not_this_person_memory
api.tests.faces.test_birth_date_face_suggestions
api.tests.faces.test_face_training_safety
api.tests.faces.test_face_clustering_and_training
api.tests.faces.test_person_birth_date
```

Architecture and tenant checks passed 91 tests:

```text
api.tests.infra.test_signal_receivers
api.tests.infra.test_models_do_no_io
api.tests.infra.test_owner_scope_calls
api.tests.infra.test_base_exception_handlers
api.tests.infra.test_test_data_factories
api.tests.infra.test_submodule_imports
api.tests.infra.test_module_layout
api.tests.infra.test_serializer_method_annotations
api.tests.sharing_and_public.test_cross_tenant_reads
api.tests.sharing_and_public.test_cross_tenant_writes
```

## Static checks

These checks passed from apps/backend:

```sh
ruff check .
ruff format --check .
python scripts/ruff_baseline.py
python scripts/typecheck.py
python scripts/check_dead_code.py
lint-imports --no-cache
python scripts/openapi_schema.py --check
```

The type check reported zero errors. Baselines did not grow.
All five import contracts passed. The API schema stayed unchanged.
The docs build used the pinned Node 24 and Yarn version.
The build retained an existing settings-page warning for #public-gallery-user.

## Practical limits

Mocked model responses verify data flow, ownership and update behavior.
They do not measure a VLM's ability to associate an action with a marked face.
That quality requires a separate model evaluation.
The 0.99 threshold is a score gate. It is not a calibrated accuracy guarantee.
Legacy captions need one successful grounded pass before safe local name removal.
Manual captions, including accepted AI suggestions, remain authoritative.

## Evidence

Local logs are retained in the task workspace:

```text
/Users/ashmelev/Documents/ChatGPT/Housekeeping/photo-source-review/identity-captions-20261102/
```

Use caption-privacy-tests-final.log, face-label-tests-final.log,
architecture-tests.log, static-checks-final.log and docs-build-final.log.
The GitLab issue draft is gitlab-issue.md in the same directory.
