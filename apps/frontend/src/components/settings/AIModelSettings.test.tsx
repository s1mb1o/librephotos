import {
  ApiError,
  type RemoteModelTestRequest,
  type SiteModelDownload,
  type SiteSettings,
  type SiteSettingsUpdate,
} from "@librephotos/api-client";
import { Grid, MantineProvider } from "@mantine/core";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { defined } from "../../util/defined.test-utils";
import { AIModelSettings } from "./AIModelSettings";

type SaveOptions = { onSuccess?: () => void };
const mocks = vi.hoisted(() => ({
  resetTest: vi.fn<() => void>(),
  testModel: vi.fn<(input: RemoteModelTestRequest) => void>(),
  testState: {
    variables: undefined as RemoteModelTestRequest | undefined,
    isSuccess: false,
    isPending: false,
    isError: false,
    error: null as Error | null,
  },
  save: vi.fn<(input: SiteSettingsUpdate, options?: SaveOptions) => void>(),
  follow: vi.fn<(job: SiteModelDownload | null | undefined) => SiteModelDownload | null | undefined>(job => job),
  rebuild: vi.fn<(stage: string) => void>(),
  success: vi.fn<(message: string) => void>(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../api_client/settings/hooks", () => ({
  useTestModelSettingsMutation: () => ({ mutate: mocks.testModel, reset: mocks.resetTest, ...mocks.testState }),
  useUpdateSettingsMutation: () => ({ mutate: mocks.save, isPending: false }),
  useFollowModelDownload: mocks.follow,
}));
vi.mock("../../api_client/jobs/hooks", () => ({
  useRunProcessingStageMutation: () => ({ mutate: mocks.rebuild, isPending: false }),
}));
vi.mock("../../service/notifications", () => ({ notification: { success: mocks.success } }));
vi.mock("./ScanSettings", () => ({ LABEL_SPAN: 8, CONTROL_SPAN: 4 }));

const BASE: SiteSettings = {
  allow_registration: false,
  allow_upload: false,
  skip_patterns: "",
  map_api_key: "",
  map_api_provider: "exiftool",
  map_tile_provider: "none",
  captioning_model: "lfm2_vl_450m",
  embedding_model: "openclip_vitb32",
  tagging_model: "openclip_vitb32",
  ocr_model: "none",
  face_recognition_model: "buffalo_sc",
  nextcloud_enabled: false,
  auto_create_user_directory: false,
};
const REMOTE = {
  disable_thinking: false,
  url: "http://vision.example/v1",
  model_name: "vision-model",
  has_token: true,
  revision: "unspecified",
  max_num_patches: 256,
  search_threshold: 0.15,
  similar_threshold: 0.8,
  tag_threshold: 0.25,
};

let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;

beforeAll(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  HTMLElement.prototype.scrollIntoView = vi.fn<() => void>();
  globalThis.ResizeObserver = class implements ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
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
});

beforeEach(() => {
  mocks.save.mockReset();
  mocks.testModel.mockReset();
  Object.assign(mocks.testState, {
    variables: undefined,
    isSuccess: false,
    isPending: false,
    isError: false,
    error: null,
  });
  mocks.rebuild.mockReset();
  mocks.follow.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function render(settings: SiteSettings = BASE) {
  await act(async () =>
    root.render(
      <MantineProvider env="test">
        <Grid>
          <AIModelSettings settings={settings} />
        </Grid>
      </MantineProvider>
    )
  );
}

function form(kind: "captioning" | "embedding"): HTMLFormElement {
  return defined(
    container.querySelector<HTMLFormElement>(
      `form[aria-label="${kind === "captioning" ? "sitesettings.captioning_model_header" : "aimodelsettings.embedding_model"}"]`
    )
  );
}

async function selectProvider(kind: "captioning" | "embedding", label: string) {
  const selector = defined(form(kind).querySelector<HTMLInputElement>('input[aria-haspopup="listbox"]'));
  await act(async () => selector.click());
  const option = defined(
    [...document.querySelectorAll<HTMLElement>('[role="option"]')].find(node => node.textContent?.trim() === label)
  );
  await act(async () => option.click());
}

function field(target: HTMLFormElement, label: string): HTMLInputElement {
  const node = defined([...target.querySelectorAll("label")].find(candidate => candidate.textContent === label));
  return defined(target.querySelector<HTMLInputElement>(`#${node.htmlFor}`));
}

async function type(input: HTMLInputElement, value: string) {
  const setter = defined(Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set);
  await act(async () => {
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("AI model settings", () => {
  it("shows remote fields only after OpenAI API is selected and preserves them while switching", async () => {
    await render();
    expect(form("captioning").querySelector('input[type="password"]')).toBeNull();
    await selectProvider("captioning", "aimodelsettings.openai_api");
    expect(field(form("captioning"), "aimodelsettings.access_token").type).toBe("password");
    await type(field(form("captioning"), "aimodelsettings.url"), "http://vision.example/v1");
    await selectProvider("captioning", "sitesettings.model_none");
    expect(form("captioning").querySelector('input[type="password"]')).toBeNull();
    await selectProvider("captioning", "aimodelsettings.openai_api");
    expect(field(form("captioning"), "aimodelsettings.url").value).toBe("http://vision.example/v1");
  });

  it("submits URL, a new masked token, and model name with the selected caption provider", async () => {
    await render();
    await selectProvider("captioning", "aimodelsettings.openai_api");
    const target = form("captioning");
    await type(field(target, "aimodelsettings.url"), "http://vision.example/v1");
    await type(field(target, "aimodelsettings.access_token"), "new-token");
    await type(field(target, "aimodelsettings.model_name"), "vision-model");
    await act(async () => {
      target.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    const payload = defined(mocks.save.mock.calls[0])[0];
    expect(payload).toMatchObject({
      captioning_model: "openai_api",
      captioning_api: {
        url: "http://vision.example/v1",
        token: "new-token",
        model_name: "vision-model",
      },
    });
  });

  it("can select a local model without submitting incomplete remote fields", async () => {
    await render();
    await selectProvider("embedding", "SigLIP2 NaFlex");
    await type(field(form("embedding"), "aimodelsettings.url"), "incomplete");
    await selectProvider("embedding", "OpenCLIP");
    await act(async () => form("embedding").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
    expect(defined(mocks.save.mock.calls[0])[0]).toEqual({ embedding_model: "openclip_vitb32" });
  });

  it("restores saved settings without placing a stored token in the field", async () => {
    await render({ ...BASE, captioning_model: "openai_api", captioning_api: REMOTE });
    expect(field(form("captioning"), "aimodelsettings.url").value).toBe(REMOTE.url);
    expect(field(form("captioning"), "aimodelsettings.model_name").value).toBe(REMOTE.model_name);
    expect(field(form("captioning"), "aimodelsettings.access_token").value).toBe("");
    expect(field(form("captioning"), "aimodelsettings.access_token").placeholder).toBe("aimodelsettings.token_saved");
  });

  it("offers SigLIP2 and sends an explicit index rebuild action", async () => {
    await render({
      ...BASE,
      embedding_status: {
        selected_model: "siglip2_naflex",
        active_model: "openclip_vitb32",
        reindex_required: true,
        job: null,
      },
    });
    await selectProvider("embedding", "SigLIP2 NaFlex");
    expect(field(form("embedding"), "aimodelsettings.model_name").value).toBe("siglip2-so400m-patch16-naflex");
    expect(container.textContent).toContain("aimodelsettings.reindex_required");
    const build = defined(
      [...container.querySelectorAll("button")].find(button => button.textContent === "aimodelsettings.build_index")
    );
    await act(async () => build.click());
    expect(mocks.rebuild).toHaveBeenCalledWith("search");
  });

  it("warns before saving an embedding model change", async () => {
    await render();
    expect(container.textContent).not.toContain("aimodelsettings.unsaved_index_change");
    await selectProvider("embedding", "SigLIP2 NaFlex");
    expect(container.textContent).toContain("aimodelsettings.unsaved_index_change");
  });

  it("follows the running embedding job using the shared job poller", async () => {
    const job = { id: 7, status: "running", progress_current: 16, progress_target: 100 };
    await render({
      ...BASE,
      embedding_status: {
        selected_model: "siglip2_naflex",
        active_model: "openclip_vitb32",
        reindex_required: true,
        job,
      },
    });
    expect(mocks.follow).toHaveBeenCalledWith(job);
    expect(container.textContent).toContain("aimodelsettings.job_progress");
  });
});

async function clickTest(kind: "captioning" | "embedding") {
  const button = defined(
    [...form(kind).querySelectorAll("button")].find(node => node.textContent === "aimodelsettings.test")
  );
  await act(async () => button.click());
  return button;
}

describe("test model settings before saving", () => {
  it("tests the draft URL, token, and model without saving or rebuilding", async () => {
    await render({ ...BASE, captioning_model: "openai_api", captioning_api: REMOTE });
    await type(field(form("captioning"), "aimodelsettings.url"), "http://draft.example/v1");
    await type(field(form("captioning"), "aimodelsettings.access_token"), "draft-token");
    await type(field(form("captioning"), "aimodelsettings.model_name"), "draft-model");
    await clickTest("captioning");
    expect(defined(mocks.testModel.mock.calls[0])[0]).toMatchObject({
      kind: "captioning",
      settings: { url: "http://draft.example/v1", token: "draft-token", model_name: "draft-model" },
    });
    expect(mocks.save).not.toHaveBeenCalled();
    expect(mocks.rebuild).not.toHaveBeenCalled();
  });
  it("validates the draft before sending a test and hides Test for local models", async () => {
    await render();
    expect(container.textContent).not.toContain("aimodelsettings.test");
    await selectProvider("captioning", "aimodelsettings.openai_api");
    await clickTest("captioning");
    expect(mocks.testModel).not.toHaveBeenCalled();
    expect(container.textContent).toContain("aimodelsettings.invalid_url");
  });
  it("shows the test result and removes it when draft settings change", async () => {
    const settings = { ...BASE, captioning_model: "openai_api", captioning_api: REMOTE };
    await render(settings);
    await clickTest("captioning");
    mocks.testState.variables = defined(mocks.testModel.mock.calls[0])[0];
    mocks.testState.isSuccess = true;
    await render(settings);
    expect(form("captioning").textContent).toContain("aimodelsettings.test_caption_success");
    await type(field(form("captioning"), "aimodelsettings.model_name"), "changed-model");
    expect(form("captioning").textContent).not.toContain("aimodelsettings.test_caption_success");
  });
  it("shows a sanitized provider error inline", async () => {
    const settings = { ...BASE, embedding_model: "siglip2_naflex", embedding_api: REMOTE };
    await render(settings);
    await clickTest("embedding");
    mocks.testState.variables = defined(mocks.testModel.mock.calls[0])[0];
    mocks.testState.isError = true;
    mocks.testState.error = new ApiError(
      400,
      "/sitesettings/test-model/",
      "private transport detail",
      undefined,
      "Model provider returned HTTP 401."
    );
    await render(settings);
    expect(form("embedding").textContent).toContain("Model provider returned HTTP 401.");
    expect(form("embedding").textContent).not.toContain("private transport detail");
  });
});
