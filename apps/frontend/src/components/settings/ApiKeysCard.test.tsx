import type { APIKeyCreated, APIKeyCreateRequest } from "@librephotos/api-client";
import { MantineProvider } from "@mantine/core";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { ApiKeysCard } from "./ApiKeysCard";

const mock = vi.hoisted(() => ({
  create: vi.fn<(values: APIKeyCreateRequest, options: { onSuccess: (data: APIKeyCreated) => void }) => void>(),
  pickerChange: (_value: string | null) => {},
  reset: vi.fn<() => void>(),
  revoke: vi.fn<(id: string, options: { onSuccess: () => void }) => void>(),
}));
vi.mock("../../api_client/auth/hooks/useApiKeys", () => ({
  useApiKeys: () => ({
    data: { results: [], count: 0 },
    isPending: false,
    isError: false,
    isFetching: false,
    refetch: async () => {},
  }),
  useCreateApiKey: () => ({ mutate: mock.create, reset: mock.reset, isPending: false }),
  useRevokeApiKey: () => ({ mutate: mock.revoke, isPending: false }),
}));
vi.mock("@mantine/dates", () => ({
  DateTimePicker: ({ onChange }: { onChange: (value: string | null) => void }) => {
    mock.pickerChange = onChange;
    return null;
  },
}));
vi.mock("../common/EmptyState", () => ({ EmptyState: ({ description }: { description: string }) => description }));
vi.mock("./SettingsSection", () => ({ SectionLink: () => null }));
beforeAll(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  await i18n.changeLanguage("en");
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
  globalThis.ResizeObserver = class implements ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});
let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
beforeEach(async () => {
  vi.clearAllMocks();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () =>
    root.render(
      <MantineProvider>
        <ApiKeysCard />
      </MantineProvider>
    )
  );
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
describe("API key settings", () => {
  it("defaults to read-only permissions", () => {
    const inputs = Array.from(container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'));
    expect(inputs.filter(input => input.checked).map(input => input.value)).toEqual(["photos:read", "jobs:read"]);
    expect(container.textContent).toContain("Create a separate key for each script or integration.");
  });
  it("does not submit an empty key name", async () => {
    const button = Array.from(container.querySelectorAll("button")).find(item => item.textContent === "Create key");
    if (!button) throw new Error("Create button missing");
    await act(async () => button.click());
    expect(mock.create).not.toHaveBeenCalled();
  });
});

async function fillName(): Promise<void> {
  const input = container.querySelector("input");
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  if (!input || !setter) throw new Error("Name input missing");
  await act(async () => {
    setter.call(input, "MCP");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function createKey(): Promise<void> {
  const button = Array.from(container.querySelectorAll("button")).find(item => item.textContent === "Create key");
  if (!button) throw new Error("Create button missing");
  await act(async () => button.click());
}

it("does not silently create a permanent key from an invalid expiration", async () => {
  await fillName();
  await act(async () => mock.pickerChange("invalid"));
  await createKey();
  expect(mock.create).not.toHaveBeenCalled();
});

it("sends a valid expiration and displays the secret once", async () => {
  await fillName();
  await act(async () => mock.pickerChange("2030-01-02 03:04:05"));
  await createKey();
  const call = mock.create.mock.calls[0];
  if (!call) throw new Error("Creation was not submitted");
  expect(call[0].expires_at).not.toBeNull();
  await act(async () =>
    call[1].onSuccess({
      id: "12345678-1234-4234-8234-123456789012",
      key: "lp_display_once",
      name: "MCP",
      permissions: ["photos:read"],
      created_at: "2026-11-02T00:00:00Z",
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
    })
  );
  expect(document.body.querySelector<HTMLInputElement>('input[aria-label="API key"]')?.value).toBe("lp_display_once");
  await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(document.body.querySelector<HTMLInputElement>('input[aria-label="API key"]')?.value).toBe("lp_display_once");
});
