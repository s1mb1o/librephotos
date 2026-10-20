# Recent caption job results

Date: 2026-11-02.
Status: Implemented, deployed to docker-srv and verified on the authenticated job page.

## User behavior

Show the latest 20 processed photos on Generate Captions job pages.
Show a thumbnail, generated caption, outcome and processing time.
Put the newest result first. Link each preview to its photo page.
Refresh while the job runs. Fetch the final results before polling stops.
Keep recorded results after completion, failure or cancellation.
Show loading, empty and failed-request states separately.
Use theme colors and support narrow screens.

## Storage

Add recent_photos, a bounded JSON list on LongRunningJob.
Keep it separate from result so cancellation and error reporting cannot erase it.
Store photo UUID, caption snapshot, status, timestamp and a truncation flag.
Cap captions at 8192 characters and retain at most 20 records.
A retry replaces the previous record for that photo within the job.
Use a row lock for updates. Preserve concurrent counters, errors and cancellation.
Do not append after the job is cancelled or finished.
Record the snapshot and advance the caption counter in one transaction.
Do not hold a job lock during model inference.

A new table would add lifecycle and retention code for this small fixed window.
Reading PhotoCaption.updated_at cannot prove membership in this job.
The bounded job field provides durable results without reconstructing history.
Earlier completed photos are not backfilled from timestamps.

## API

Add GET /api/jobs/<int:pk>/recent-photos/.
Return finished, limit and results through a declared serializer.
Each result has photo_id, image_hash, caption, status, processed_at and truncated.
Permit the job owner only. Filter photos by current ownership and availability.
Hide removed and trashed photos. Other users, including staff, cannot read the feed.
Do not add the private backing field to existing job or queue serializers.
The existing default-deny API-key policy excludes this new browser endpoint.
No provider credentials or internal face evidence are exposed.
The read endpoint does not run a model or change photo metadata.

## Client

Declare the endpoint and zod response in packages/api-client.
Use a jobKeys factory key and a thin frontend query hook.
Poll until the feed response reports finished. This retains the final window.
Add a Recent processed photos card only for caption jobs.
Explain that a caption is a snapshot from processing time.
Keep long captions bounded and indicate truncation. Open the photo for its current caption.

## Verification

Test the retention limit, retry deduplication and snapshot ordering.
Test cancellation, concurrent error data and counter preservation.
Test successful, failed and disabled caption processing.
Test anonymous, other-user, staff, deleted-photo and API-key access.
Test constant query count, schema contracts and frontend loading/error/empty states.
Test polling through the final completion response.
Run relevant backend, API-client, web, mobile and documentation checks.
Use synthetic images and mocked model output. Do not start inference for tests.
