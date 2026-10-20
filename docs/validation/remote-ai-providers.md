# Remote AI provider validation

Date: 2026-11-01
Branch: `codex/remote-ai-providers`
Related issues: #1 and #2.

## Verified behavior

- Admin Area offers OpenAI API captioning and SigLIP2 NaFlex embeddings.
- Remote settings persist. Saved tokens are encrypted and never returned.
- Caption requests carry image data and the existing prompt context.
- Remote captions retain the provider, model name, and image hash.
- SigLIP2 vectors have 1152 finite values and are normalized.
- Model profiles have separate database caches and persistent index namespaces.
- Profile changes show a rebuild notice in Admin Area and each user's Library.
- A build captures one profile. A later settings change does not change that build.
- Failure and cancellation retain completed batches and the previous active profile.
- A failed return to OpenCLIP does not activate an incomplete replacement.
- A checkpoint revision change behind the same model handle pauses text semantic search.
  Metadata search and cached image similarity remain available.
- Generated Things preserve manual Tags, captions, and ratings.

## Automated checks

The tests use temporary data. They do not mount the production photo library.

| Check | Result |
| --- | --- |
| Full frontend and shared API-client suite | 4,395 passed; 9 skipped |
| Backend search, remote captions, and request timeouts | 244 passed |
| Local captioning, caption jobs, model requirements, and replaced-file cleanup | 191 passed |
| Tenant isolation, API conventions, owner scopes, migration sync, and replaced-file cleanup | 607 passed |
| Docker image guards, standalone smoke, and updater tests | 104 ran; 1 skipped; no failures |
| Backend ruff, formatting, and baseline check | Pass; no baseline growth |
| Backend mypy | Zero errors; empty baseline |
| Backend dead code and import contracts | Pass; five contracts kept |
| Migration synchronization | No changes detected |
| Frontend TypeScript, e2e TypeScript, ESLint, formatting, and Knip | Pass |
| Shared API-client standalone TypeScript and ESLint | Pass with the frontend dependencies |
| Frontend production build | Pass |
| Documentation production build | Pass |

The final model-switch UI tests also cover selecting a local model with
incomplete remote fields. They ran after the full frontend suite.
The schema includes the new settings and index status fields.
The shared API contract comparison passes.

## Live gateway check

A temporary synthetic JPEG had a red square and a blue circle on white.
Its size was 640 by 320 pixels.
The check used the existing GX10 gateway at `192.168.86.14:18081`.
No production photo was sent.
No model service was restarted or reconfigured.

The SigLIP2 client returned normalized 1152-dimensional vectors.
The matching text scored 0.2119.
An unrelated landscape description scored -0.0337.
The caption client used the resident `qwen3.5-9b-nvfp4` model.
The request explicitly set `chat_template_kwargs.enable_thinking=false`.
The response correctly described the two shapes.
This checks integration. It does not measure retrieval or label quality.

## Limits

The broad historical backend suite exceeded the Mac Docker VM's memory limit.
The relevant tests were run in bounded groups instead.
An initial shallow `/code` mount also prevented three infrastructure imports.
The final checks use the complete repository under `/repo/apps/backend`.

Three unchanged face alignment tests fail in the deployed AMD64 image under
Mac emulation. Their tolerance is 1e-12. Observed differences are about
2e-6 to 7.5e-6. This change does not alter face alignment.
The documentation build retains an existing `#public-gallery-user` anchor warning.

No representative photo quality benchmark has been completed.
The cosine thresholds are initial values. They require calibration.
Interrupted jobs retain cached vectors but do not resume automatically.
Cancel an interrupted running job before starting another build.

## Deployment state

This implementation has not replaced the running docker-srv image.
The initial library scan was still active at validation time.
It had processed 24,306 of 35,274 groups and created 22,830 photo rows.
The production provider selection remains unchanged.
No full-library remote reindex was started.
