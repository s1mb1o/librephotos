# Face-grounded caption updates

Date: 2026-11-02.
Status: Implemented. Local checks passed. Not deployed.
Issue destination: awaiting the owner's GitLab project URL.

## Behavior

A generated caption can change from "a person is wearing a hat" to
"Alexander is wearing a hat" after a trusted face identity becomes available.
The VLM receives the full thumbnail with numbered face boxes and textual xyxy
coordinates. It refers to faces with stable tokens such as `[[face:12]]`.
LibrePhotos resolves each token to a trusted name or "a person".
The VLM does not receive personal names from the face database.
Do not replace arbitrary words such as "person" in a free-text caption.

## Identity gate

A confirmed Face.person label can use a named USER person of the photo owner.
Imported named face regions use this same existing label field.
An inferred face requires both classification and clustering to name that same
USER person. Both finite scores MUST be at least max(0.99, user.confidence_person).
These scores are model scores. They are not calibrated correctness probabilities.
Reject unknown and cluster labels, rejected identities, cross-owner people,
deleted faces, later video frames, invalid boxes, and inferred faces without an
encoding. Omit a contradictory identity for a person born after the photo.
A user's caption context and add_person switches continue to control naming.

## Stored state

Use versioned captioning_identity metadata in PhotoCaption.captions_json.
Store the raw token template, source image hash, geometry fingerprint,
identity fingerprint, annotated boxes, resolved identity provenance, stale state,
and the latest pending fingerprint. Preserve im2txt and user_caption keys.
No schema migration is required.
Internal identity metadata MUST NOT appear in photo responses or shared search.

Names can be rebound without inference when the source and face geometry match.
Remove a name immediately when its confidence or assignment no longer qualifies.
Changed geometry or a missing face reference queues a fresh VLM request.
An older queued fingerprint MUST NOT replace a newer context.
Recheck the context after inference. Merge into the latest locked caption row.
Never overwrite a manual caption that changed while the VLM was running.

## Updates and retry

Handle face saves and deletions, person names and deletion, face-label bulk edits,
undo and merges, bulk prediction writes, rejected people, and caption context
settings. Use transaction.on_commit and the existing enqueue_task entrypoint.
Do not make model or network calls in a request's signal handler.
Skip photos without a generated caption. Initial generation uses current faces.
Deduplicate identical pending fingerprints. Supersede older queued work.
A failed refresh leaves stale state for retry and retains a safe generated caption.
Generate captions includes stale captions. Its existing full_scan action remains
available to refresh old untracked captions. Originals are not edited.

## Limits

VLM face-to-action grounding can still be wrong. Bounding boxes provide evidence;
recognition confidence alone does not prove that grounding is correct.
A model that omits reference tokens can leave a caption anonymous.
Legacy generated captions have no face template. A fresh VLM pass is required.
Do not infer replacements inside a legacy caption from an unknown prior name.

## Verification

Test confirmed, uncertain, agreeing and conflicting predictions, nonfinite scores,
rejections, owners, unknown labels, dates, geometry, multiple people and videos.
Test exact token replacement and unknown-token anonymization.
Test initial generation, later identification, rename, correction, undo, deletion,
confidence loss, bulk prediction hooks, context switches, stale jobs and retries.
Test provider failure and a face or manual caption change during inference.
Verify search captions update. Verify original thumbnails and photos are unchanged.
Run relevant backend tests, lint, types, import guards and the documentation build.
Use synthetic fixtures. Do not send private library photos to a provider for tests.

## Validation result

The caption, confidence and sharing group passed 114 tests.
The face-label and classifier regression group passed 135 tests.
Architecture and tenant guards passed 91 tests.
Backend lint, formatting, baseline checks, types, dead code, import contracts,
and the OpenAPI schema check passed.
The documentation build passed with one existing unrelated anchor warning.
See docs/validation/identity-aware-captions.md for commands and limits.
