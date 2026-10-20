import type { RecentJobPhoto, RecentJobPhotos as RecentPhotos } from "@librephotos/api-client";
import React from "react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { click, renderInMantine, setUpMantineDom } from "../modals/confirmModal.test-utils";
import { RecentJobPhotos } from "./RecentJobPhotos";

const stubs = vi.hoisted(() => ({
  data: undefined as RecentPhotos | undefined,
  loading: false,
  error: false,
  fetching: false,
  navigate: vi.fn<(options: unknown) => void>(),
  userId: 1 as number | null,
  refetch: vi.fn<() => Promise<unknown>>(async () => undefined),
}));

vi.mock("../../api_client/jobs/hooks", () => ({
  useRecentJobPhotosQuery: () => ({
    data: stubs.data,
    isLoading: stubs.loading,
    isError: stubs.error,
    isFetching: stubs.fetching,
    refetch: stubs.refetch,
  }),
}));
vi.mock("../common/MediaThumbnail", () => ({
  MediaThumbnail: ({ imageHash, alt = "" }: { imageHash: string; alt?: string }) => (
    <img alt={alt} data-hash={imageHash} />
  ),
}));
vi.mock("../../hooks/useAuth", () => ({ useAuth: () => ({ userId: stubs.userId }) }));
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => stubs.navigate,
  Link: ({
    params,
    children,
    "aria-label": label,
  }: {
    params: { id: string };
    children: ReactNode;
    "aria-label"?: string;
  }) => (
    <a href={`/photo/${params.id}`} aria-label={label}>
      {children}
    </a>
  ),
}));

const PHOTO: RecentJobPhoto = {
  photo_id: "photo-1",
  image_hash: "hash-1",
  caption: "A person is wearing a hat.",
  status: "success",
  processed_at: "2026-11-02T10:00:00Z",
  truncated: false,
};

beforeAll(async () => {
  setUpMantineDom();
  await i18n.changeLanguage("en");
});
beforeEach(() => {
  document.body.innerHTML = "";
  stubs.data = undefined;
  stubs.loading = false;
  stubs.error = false;
  stubs.fetching = false;
  stubs.refetch.mockClear();
  stubs.userId = 1;
});

async function renderCard() {
  return renderInMantine(<RecentJobPhotos jobId={25} ownerId={1} />);
}

describe("recent caption results", () => {
  it("shows the result, status, preview link and processing timestamp", async () => {
    stubs.data = { finished: false, limit: 20, results: [PHOTO] };
    const { container } = await renderCard();
    expect(container.textContent).toContain("A person is wearing a hat.");
    expect(container.textContent).toContain("Caption generated");
    expect(container.querySelector("a")?.getAttribute("href")).toBe("/photo/photo-1");
    expect(container.querySelector("img")?.dataset.hash).toBe("hash-1");
    expect(container.querySelector("time")?.getAttribute("datetime")).toBe(PHOTO.processed_at);
  });

  it("keeps server order and displays failed, skipped and shortened output", async () => {
    stubs.data = {
      finished: true,
      limit: 20,
      results: [
        { ...PHOTO, caption: "Newest", truncated: true },
        { ...PHOTO, photo_id: "photo-2", caption: "", status: "failed" },
        { ...PHOTO, photo_id: "photo-3", caption: "", status: "skipped" },
      ],
    };
    const { container } = await renderCard();
    expect([...container.querySelectorAll("a")].map(a => a.getAttribute("href"))).toEqual([
      "/photo/photo-1",
      "/photo/photo-2",
      "/photo/photo-3",
    ]);
    expect(container.textContent).toContain("Caption failed");
    expect(container.textContent).toContain("Skipped");
    expect(container.textContent).toContain("This result is shortened");
    expect(container.textContent).toContain("See this job’s errors");
  });

  it("distinguishes loading, an empty window, and a failed request with retry", async () => {
    stubs.loading = true;
    let view = await renderCard();
    expect(view.container.textContent).toContain("Loading recent photos");
    expect(view.container.textContent).not.toContain("No recent results yet");
    document.body.innerHTML = "";
    stubs.loading = false;
    stubs.data = { finished: false, limit: 20, results: [] };
    view = await renderCard();
    expect(view.container.textContent).toContain("No recent results yet");
    document.body.innerHTML = "";
    stubs.data = undefined;
    stubs.error = true;
    view = await renderCard();
    expect(view.container.textContent).not.toContain("No recent results yet");
    const retry = [...view.container.querySelectorAll("button")].find(button => button.textContent?.includes("Retry"));
    if (!retry) throw new Error("No retry button");
    await click(retry);
    expect(stubs.refetch).toHaveBeenCalledTimes(1);
  });

  it("keeps existing results after a failed background refresh and escapes model text", async () => {
    stubs.data = { finished: false, limit: 20, results: [{ ...PHOTO, caption: "<script>unsafe()</script>" }] };
    stubs.error = true;
    const { container } = await renderCard();
    expect(container.textContent).toContain("<script>unsafe()</script>");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});

it("hides another user's photo results on an administrator job page", async () => {
  stubs.userId = 2;
  stubs.data = { finished: true, limit: 20, results: [PHOTO] };
  const { container } = await renderCard();
  expect(container.textContent).not.toContain("Recent processed photos");
  expect(container.textContent).not.toContain(PHOTO.caption);
});
