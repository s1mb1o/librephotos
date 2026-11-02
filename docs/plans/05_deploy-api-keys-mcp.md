# Deploy API keys and MCP

Date: 2026-11-02

The owner authorized push, deployment, testing, and corrective changes.
The owner selected persistent HTTP bearer tokens. Do not use Claude reviews.

Integrate the deployed model-settings Test action before deployment.
Preserve the current captioning configuration and all photo metadata.
Use an isolated checkout. Keep the main checkout available to its other thread.

For MCP HTTP, use separate high-entropy persistent tokens.
Store only SHA-256 token verifiers in the service's protected credentials directory.
Map each verifier to an account and its distinct scoped LibrePhotos API key.
Never forward MCP bearer tokens to LibrePhotos.
Require authentication on every HTTP endpoint. Reject missing or revoked tokens.
Reload token verifiers on each request. Keep write tools disabled by default.

Deploy the application through its existing frozen-catalog migration helper.
Deploy MCP as a separate non-root container on the existing Docker network.
Use LAN address `192.168.86.16:19851`. Do not add a WAN route.
Store the client token in macOS Keychain. Keep credentials outside Git and images.

Validate backend and frontend integration, MCP identity isolation, revocation,
real photo search, authenticated previews, denied writes, and container health.
Record source commits, image tags, recovery checkpoints, and test results.
