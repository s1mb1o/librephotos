import { describe, expect, it } from "vitest";
import * as endpoints from "../endpoints";
import { APIKey } from "../schemas";
import { defined } from "./defined";
import { fakeServer } from "./harness";

const item = {
  id: "12345678-1234-4234-8234-123456789012",
  name: "script",
  permissions: ["photos:read"],
  created_at: "2026-11-02T00:00:00Z",
  expires_at: null,
  last_used_at: null,
  revoked_at: null,
};

describe("API keys", () => {
  it("reads one bounded page", async () => {
    const page = { count: 1, next: null, previous: null, results: [item] };
    const { client, requests } = fakeServer(page);
    await expect(endpoints.fetchAPIKeys(client, 2)).resolves.toEqual(page);
    expect(defined(requests[0]).url).toContain("/auth/keys/?page=2&page_size=25");
  });
  it("returns the one-time creation secret", async () => {
    const { client } = fakeServer({ ...item, key: "lp_id.secret" });
    await expect(
      endpoints.createAPIKey(client, {
        name: "script",
        permissions: ["photos:read"],
        expires_at: null,
      })
    ).resolves.toMatchObject({ key: "lp_id.secret" });
    expect(APIKey.parse({ ...item, key: "secret", verifier: "hash" })).not.toHaveProperty("key");
  });
  it("revokes one key without parsing an empty response", async () => {
    const { client, requests } = fakeServer({});
    await endpoints.revokeAPIKey(client, item.id);
    expect(defined(requests[0]).method).toBe("DELETE");
  });
});
