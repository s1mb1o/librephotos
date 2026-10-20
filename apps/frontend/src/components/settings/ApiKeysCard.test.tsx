import type { APIKeyCreated, APIKeyCreateRequest } from "@librephotos/api-client";
import { MantineProvider } from "@mantine/core";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { ApiKeysCard } from "./ApiKeysCard";

const mock = vi.hoisted(() => ({
  create: vi.fn<(values: APIKeyCreateRequest, options: { onSuccess: (data: APIKeyCreated) => void }) => void>(),
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
vi.mock("../common/EmptyState", () => ({ EmptyState: () => null }));
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
    expect(container.textContent).toContain("Leave empty for no expiration.");
  });
  it("does not submit an empty key name", async () => {
    const button = Array.from(container.querySelectorAll("button")).find(item => item.textContent === "Create key");
    if (!button) throw new Error("Create button missing");
    await act(async () => button.click());
    expect(mock.create).not.toHaveBeenCalled();
  });
});
