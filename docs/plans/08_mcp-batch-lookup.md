# Batch file lookup for LibrePhotos MCP

Date: 2026-11-06.

## Contract

Add the read tool `check_files_exist` with a `md5s` array of 1 to 100 digests.
Each digest MUST contain 32 hexadecimal characters.
Accept uppercase input and return lowercase digests.
Return one result per input in the same order, including repeated digests.
Each result contains `md5`, `exists`, and `photo_id`.
Return `exists: false` and `photo_id: null` for a digest with no match.
Keep `check_file_exists` available for existing clients.

## Catalog lookup

Add `GET /api/integrations/files/exists/` with repeated `md5` parameters.
Use the same `photos:read` permission and owner scope as the single lookup.
Match the historical photo hash and linked file hashes.
Accept both the bare digest and the digest with the caller's owner suffix.
Choose the lowest photo UUID when more than one photo matches.
Use two indexed branches in one SQL statement. Read only hashes and UUIDs.
Read no original files and make no database schema change.

## Folder check

Hash local files and deduplicate the digests before sending requests.
Send at most 100 unique digests per request. Preserve file order in the report.
Validate the complete batch before applying its results.
Keep files from a failed or unsent batch unchecked.
Retain results from earlier successful batches.

## Verification

Compare the batch and single results for matches and misses.
Test both hash sources, UUID selection, duplicate input, and uppercase input.
Check malformed and oversized requests and cross-account access.
Check that a 100-digest request uses one catalog query.
Verify that MCP sends one upstream request for one batch.
Compare the live folder results and timing after deployment.
