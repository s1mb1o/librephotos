# Remote captioning and semantic embeddings

Date: 2026-11-01
Status: Implemented. Correctness validation is recorded in the
[validation report](../validation/remote-ai-providers.md).
The owner authorized issues #1 and #2. Deployment and quality calibration remain separate.

## Scope

Add `OpenAI API` to `Captioning Model` on `/admin`.
Show `URL`, `Access Token`, and `Model name` when selected.
Add an embedding selector for local OpenCLIP and remote SigLIP2 NaFlex.
Save remote connection settings through the same admin page.
Keep the existing local defaults and the captioning `None` option.

## Data and credentials

Store remote settings in a database model.
Encrypt access tokens with the existing django-cryptography integration.
Accept token updates only through the admin-only settings POST.
Never return saved tokens in a settings response.
Return a `has_token` flag to administrators.
An omitted or blank token preserves the saved token.
An explicit clear action removes the saved token.
Do not expose remote URLs or model configuration in the anonymous settings GET.

Store each remote embedding profile under a stable configuration fingerprint.
Include provider, endpoint, model, revision, preprocessing, patch budget,
dimension, and normalization in the fingerprint.
Store per-photo vectors separately from the existing OpenCLIP columns.
Record the active profile separately for each user.
Keep different profiles in separate similarity index namespaces.

## Requests

Caption requests use `POST {base_url}/chat/completions`.
Send the existing prompt and a JPEG data URL in the user message.
Return the final assistant text through the existing caption storage path.
Preserve manual captions and the existing optional context.

Embedding requests use `POST {base_url}/embeddings`.
Send image data URLs or text in `input` with the configured NaFlex patch budget.
Validate response ordering, cardinality, model identity, dimensions, and values.
Use normalized 1152-dimensional vectors for SigLIP2.
Preserve the thumbnail aspect ratio.
Encode built-in and custom label phrases with the same profile.
Expose separate cosine thresholds for text search, image similarity, and labels.
Treat label cosine scores as similarity scores, not classification probabilities.

## Index replacement and jobs

Reuse the existing Calculate embeddings job and progress reporting.
Capture the selected profile at the start of the job.
Reuse already stored vectors when a new job continues an interrupted build.
Keep the existing duplicate-delivery guard. After a process restart, cancel
an interrupted running job before starting a new build.
Keep the previous active profile and index while a replacement builds.
Activate the replacement only after all required batches and the index commit succeed.
Use the active profile for both the text encoder and image similarity.
Preserve previous vectors and index files for a later switch back.
Show the selected and active models, required re-embedding, and job progress in admin.
Warn before an unsaved profile change. Show a rebuild notice on each user's Library page.
Capture the local profile as well as remote profiles during a running build.
Keep local sidecars available while any active library still needs them.
Stop unused local captioning or OpenCLIP sidecars through the existing watchdog.

## Failure behavior

Use bounded HTTP timeouts and reject redirects.
Validate HTTP/HTTPS base URLs. Reject URL credentials, query strings, and fragments.
Return actionable errors without upstream response bodies or token values.
A failed provider call must not replace a caption or activate a partial index.
Cancellation must preserve completed embedding batches for the next run.

## Verification

Test admin authorization, conditional fields, persistence, and token non-disclosure.
Test image transport, prompt context, optional authentication, and malformed replies.
Test dimensions, mixed profiles, restart persistence, cancellation, and failed replacement.
Test local provider behavior and preservation of manual metadata.
Run backend tests and types, frontend tests and types, and API contract checks.
Build documentation and the production image before deployment.
Keep representative retrieval and label-quality evaluation separate from correctness tests.
Document threshold calibration limits. Do not claim measured quality without evidence.

## Sources

- https://developers.openai.com/api/docs/guides/images-vision
- https://developers.openai.com/api/reference/resources/chat/methods/create
- https://huggingface.co/google/siglip2-so400m-patch16-naflex
- https://huggingface.co/docs/transformers/model_doc/siglip2
- Local GX10 contract: `Admin/gx10/docs/inference/image-embeddings.md`.
