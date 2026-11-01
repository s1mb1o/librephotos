# Smoke tests

## Fork initialization

- Verify that `origin` resolves to the personal GitHub fork.
- Verify that the upstream GitHub push URL is disabled.
- Verify that release `1.5.1` is an ancestor of the development branch.
- Verify that upstream branches, tags, and commit history are available.
- Verify that application files match the reviewed release at initialization.
- Verify that the published branch commit matches the local commit.
- Verify that GitHub Actions are disabled during fork initialization.

## Targets for later changes

These checks are pending. They are not passing claims for the initial fork.

- Concurrent moves to one destination preserve both original payloads.
- An interrupted cross-filesystem copy preserves the source and removes staging data.
- RAW, JPEG, Live Photo, and XMP components stay associated after a move.
- A disconnected NAS does not cause deletion of catalog entries or originals.
- Configured caption providers process a fixture and report actionable errors.
- Caption generation preserves manual captions.
- Caption export survives a fresh catalog import.
- Semantic search preserves relevance order with filters and shared libraries.
- Quality scoring records model provenance and preserves manual ratings.
- Similar-photo review requires an explicit decision before original deletion.
