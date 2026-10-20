import {
  ApiError,
  type RemoteModelTestRequest,
  type SiteSettings,
  type SiteSettingsUpdate,
} from "@librephotos/api-client";
import {
  Accordion,
  Alert,
  Anchor,
  Button,
  Checkbox,
  Grid,
  Group,
  NumberInput,
  PasswordInput,
  Progress,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { schemaResolver, useForm } from "@mantine/form";
import { Link } from "@tanstack/react-router";
import React, { useEffect, useEffectEvent } from "react";
import { useTranslation } from "react-i18next";
import { useRunProcessingStageMutation } from "../../api_client/jobs/hooks";
import {
  useFollowModelDownload,
  useTestModelSettingsMutation,
  useUpdateSettingsMutation,
} from "../../api_client/settings/hooks";
import { notification } from "../../service/notifications";
import { makeAIModelSettingsSchema } from "./AIModelSettings.schema";
import { CONTROL_SPAN, LABEL_SPAN } from "./ScanSettings";

type ModelKind = "captioning" | "embeddings";

function ModelSetting({ kind, settings }: { kind: ModelKind; settings: SiteSettings }) {
  const { t } = useTranslation();
  const { mutate, isPending } = useUpdateSettingsMutation();
  const test = useTestModelSettingsMutation();
  const stored = kind === "captioning" ? settings.captioning_api : settings.embedding_api;
  const selected = kind === "captioning" ? settings.captioning_model : (settings.embedding_model ?? "openclip_vitb32");
  const form = useForm({
    initialValues: {
      provider: selected,
      url: stored?.url ?? "",
      model_name: stored?.model_name || (kind === "embeddings" ? "siglip2-so400m-patch16-naflex" : ""),
      token: "",
      clear_token: false,
      disable_thinking: stored?.disable_thinking ?? false,
      revision: stored?.revision ?? "unspecified",
      max_num_patches: stored?.max_num_patches ?? 256,
      search_threshold: stored?.search_threshold ?? 0.15,
      similar_threshold: stored?.similar_threshold ?? 0.8,
      tag_threshold: stored?.tag_threshold ?? 0.25,
    },
    validate: schemaResolver(makeAIModelSettingsSchema(t), { sync: true }),
  });
  const load = useEffectEvent(() => {
    if (form.isDirty()) return;
    const values = {
      provider: selected,
      url: stored?.url ?? "",
      model_name: stored?.model_name || (kind === "embeddings" ? "siglip2-so400m-patch16-naflex" : ""),
      token: "",
      clear_token: false,
      disable_thinking: stored?.disable_thinking ?? false,
      revision: stored?.revision ?? "unspecified",
      max_num_patches: stored?.max_num_patches ?? 256,
      search_threshold: stored?.search_threshold ?? 0.15,
      similar_threshold: stored?.similar_threshold ?? 0.8,
      tag_threshold: stored?.tag_threshold ?? 0.25,
    };
    form.setValues(values);
    form.resetDirty(values);
  });
  useEffect(() => {
    load();
  }, [selected, stored, kind]);

  const remote = form.values.provider === "openai_api" || form.values.provider === "siglip2_naflex";
  const captioning = kind === "captioning";
  const indexSettingsChanged =
    !captioning &&
    (form.values.provider !== selected ||
      (remote &&
        (form.values.url.trim().replace(/\/+$/, "") !== (stored?.url ?? "") ||
          form.values.model_name.trim() !== (stored?.model_name || "siglip2-so400m-patch16-naflex") ||
          form.values.revision !== (stored?.revision ?? "unspecified") ||
          form.values.max_num_patches !== (stored?.max_num_patches ?? 256))));
  const heading = captioning ? t("sitesettings.captioning_model_header") : t("aimodelsettings.embedding_model");
  const options = captioning
    ? [
        { value: "lfm2_vl_450m", label: t("sitesettings.option_default", { name: "LFM2.5-VL" }) },
        { value: "openai_api", label: t("aimodelsettings.openai_api") },
        { value: "none", label: t("sitesettings.model_none") },
      ]
    : [
        { value: "openclip_vitb32", label: "OpenCLIP" },
        { value: "siglip2_naflex", label: "SigLIP2 NaFlex" },
      ];

  const { provider: _provider, ...draft } = form.values;
  const testInput: RemoteModelTestRequest = { kind, settings: draft };
  const tested = remote && JSON.stringify(test.variables) === JSON.stringify(testInput);

  const submit = form.onSubmit(values => {
    const { provider, ...config } = values;
    const update: SiteSettingsUpdate = captioning
      ? { captioning_model: provider, ...(remote ? { captioning_api: config } : {}) }
      : { embedding_model: provider, ...(remote ? { embedding_api: config } : {}) };
    mutate(update, {
      onSuccess: () => {
        test.reset();
        form.setFieldValue("token", "");
        form.setFieldValue("clear_token", false);
        form.resetDirty({ ...values, token: "", clear_token: false });
        notification.success(t("sitesettings.saved"));
      },
    });
  });

  return (
    <Grid.Col span={12}>
      <form aria-label={heading} onSubmit={submit}>
        <Grid>
          <Grid.Col span={LABEL_SPAN}>
            <Stack gap={0}>
              <Text>{heading}</Text>
              <Text fz="sm" c="dimmed">
                {captioning
                  ? t("sitesettings.captioning_model_description")
                  : t("aimodelsettings.embedding_description")}
              </Text>
            </Stack>
          </Grid.Col>
          <Grid.Col span={CONTROL_SPAN}>
            <Select aria-label={heading} allowDeselect={false} data={options} {...form.getInputProps("provider")} />
          </Grid.Col>
          {remote && (
            <Grid.Col span={12}>
              <Stack gap="sm">
                <TextInput
                  label={t("aimodelsettings.url")}
                  description={t("aimodelsettings.url_help")}
                  {...form.getInputProps("url")}
                />
                <PasswordInput
                  label={t("aimodelsettings.access_token")}
                  placeholder={stored?.has_token ? t("aimodelsettings.token_saved") : undefined}
                  description={t("aimodelsettings.token_help")}
                  {...form.getInputProps("token")}
                />
                {stored?.has_token && (
                  <Checkbox
                    label={t("aimodelsettings.clear_token")}
                    {...form.getInputProps("clear_token", { type: "checkbox" })}
                  />
                )}
                <TextInput label={t("aimodelsettings.model_name")} {...form.getInputProps("model_name")} />
                {captioning && (
                  <Checkbox
                    label={t("aimodelsettings.disable_thinking")}
                    description={t("aimodelsettings.disable_thinking_help")}
                    {...form.getInputProps("disable_thinking", { type: "checkbox" })}
                  />
                )}
                {!captioning && (
                  <Accordion variant="separated">
                    <Accordion.Item value="advanced">
                      <Accordion.Control>{t("aimodelsettings.advanced")}</Accordion.Control>
                      <Accordion.Panel>
                        <Stack gap="sm">
                          <TextInput label={t("aimodelsettings.revision")} {...form.getInputProps("revision")} />
                          <NumberInput
                            label={t("aimodelsettings.patches")}
                            min={1}
                            max={4096}
                            allowDecimal={false}
                            {...form.getInputProps("max_num_patches")}
                          />
                          <Text fz="sm" c="dimmed">
                            {t("aimodelsettings.threshold_help")}
                          </Text>
                          <NumberInput
                            label={t("aimodelsettings.search_threshold")}
                            min={-1}
                            max={1}
                            step={0.01}
                            {...form.getInputProps("search_threshold")}
                          />
                          <NumberInput
                            label={t("aimodelsettings.similar_threshold")}
                            min={-1}
                            max={1}
                            step={0.01}
                            {...form.getInputProps("similar_threshold")}
                          />
                          <NumberInput
                            label={t("aimodelsettings.tag_threshold")}
                            min={-1}
                            max={1}
                            step={0.01}
                            {...form.getInputProps("tag_threshold")}
                          />
                        </Stack>
                      </Accordion.Panel>
                    </Accordion.Item>
                  </Accordion>
                )}
              </Stack>
            </Grid.Col>
          )}
          {indexSettingsChanged && (
            <Grid.Col span={12}>
              <Alert color="yellow">{t("aimodelsettings.unsaved_index_change")}</Alert>
            </Grid.Col>
          )}
          {tested && (test.isSuccess || test.isError) && (
            <Grid.Col span={12}>
              <Alert color={test.isSuccess ? "green" : "red"} role="status">
                {test.isSuccess
                  ? captioning
                    ? t("aimodelsettings.test_caption_success")
                    : t("aimodelsettings.test_embedding_success")
                  : test.error instanceof ApiError
                    ? (test.error.serverMessage ?? t("aimodelsettings.test_failed"))
                    : t("aimodelsettings.test_failed")}
              </Alert>
            </Grid.Col>
          )}
          <Grid.Col span={12}>
            <Group justify="flex-end">
              {remote && (
                <Button
                  type="button"
                  variant="outline"
                  loading={test.isPending}
                  onClick={() => {
                    if (!form.validate().hasErrors) test.mutate(testInput);
                  }}
                >
                  {t("aimodelsettings.test")}
                </Button>
              )}
              <Button type="submit" loading={isPending}>
                {t("aimodelsettings.save")}
              </Button>
            </Group>
          </Grid.Col>
        </Grid>
      </form>
    </Grid.Col>
  );
}

export function EmbeddingIndexStatus({ settings }: { settings: SiteSettings }) {
  const { t } = useTranslation();
  const status = settings.embedding_status;
  const job = useFollowModelDownload(status?.job);
  const { mutate, isPending } = useRunProcessingStageMutation();
  if (!status) return null;
  const model = status.active_model === "openclip_vitb32" ? "OpenCLIP" : "SigLIP2 NaFlex";
  const state =
    job?.status === "running"
      ? "running"
      : job?.status === "failed"
        ? "failed"
        : job?.status === "cancelled"
          ? "cancelled"
          : "finished";
  return (
    <Grid.Col span={12}>
      <Stack gap="sm">
        <Text fz="sm">{t("aimodelsettings.active_model", { model })}</Text>
        {status.reindex_required && (
          <Alert color={status.text_search_paused ? "yellow" : "blue"}>
            {status.text_search_paused
              ? t("aimodelsettings.text_search_paused")
              : t("aimodelsettings.reindex_required", { model })}
          </Alert>
        )}
        {job && (
          <>
            <Text fz="sm">
              {t("aimodelsettings.job_progress", {
                state: t(`aimodelsettings.job_${state}`),
                current: job.progress_current,
                total: job.progress_target,
              })}
            </Text>
            <Progress
              aria-label={t("aimodelsettings.index_progress")}
              value={job.progress_target ? (100 * job.progress_current) / job.progress_target : 0}
            />
            {job.status === "failed" && (
              <Anchor component={Link} to="/jobs">
                {t("aimodelsettings.job_details")}
              </Anchor>
            )}
          </>
        )}
        <Text fz="sm" c="dimmed">
          {t("aimodelsettings.build_help")}
        </Text>
        <Group justify="flex-end">
          <Button variant="outline" loading={isPending || job?.status === "running"} onClick={() => mutate("search")}>
            {t("aimodelsettings.build_index")}
          </Button>
        </Group>
      </Stack>
    </Grid.Col>
  );
}

export function AIModelSettings({ settings }: { settings: SiteSettings }) {
  return (
    <>
      <ModelSetting kind="captioning" settings={settings} />
      <ModelSetting kind="embeddings" settings={settings} />
      <EmbeddingIndexStatus settings={settings} />
    </>
  );
}
