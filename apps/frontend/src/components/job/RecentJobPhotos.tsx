import type { RecentJobPhoto } from "@librephotos/api-client";
import { Badge, Card, Group, Paper, Stack, Text, Title } from "@mantine/core";
import { IconPhoto } from "@tabler/icons-react";
import { Link } from "@tanstack/react-router";
import { DateTime } from "luxon";
import React from "react";
import { useTranslation } from "react-i18next";
import { useRecentJobPhotosQuery } from "../../api_client/jobs/hooks";
import { useAuth } from "../../hooks/useAuth";
import { parseInstant } from "../../util/dateUtils";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { MediaThumbnail } from "../common/MediaThumbnail";
import { PageLoader } from "../common/PageLoader";
import { useListFailure } from "../common/useListFailure";
import classes from "./RecentJobPhotos.module.css";

const OUTCOME_COLOR = { success: "green", failed: "red", skipped: "gray" };
const OUTCOME_LABEL = {
  success: "joblist.recent.success",
  failed: "joblist.recent.failed",
  skipped: "joblist.recent.skipped",
} as const;

function ProcessedPhoto({ result }: Readonly<{ result: RecentJobPhoto }>) {
  const { t } = useTranslation();
  return (
    <Paper withBorder p="sm">
      <Group align="flex-start" wrap="nowrap">
        <Link to="/photo/$id" params={{ id: result.photo_id }} aria-label={t("joblist.recent.openphoto")}>
          <MediaThumbnail imageHash={result.image_hash} size={80} video={false} radius="sm" />
        </Link>
        <Stack gap="xs" flex={1} miw={0}>
          <Group gap="xs">
            <Badge color={OUTCOME_COLOR[result.status]} variant="light">
              {t(OUTCOME_LABEL[result.status])}
            </Badge>
            <Text size="xs" c="dimmed" component="time" dateTime={result.processed_at}>
              {parseInstant(result.processed_at).toLocaleString(DateTime.DATETIME_MED_WITH_SECONDS)}
            </Text>
          </Group>
          <Text size="sm" className={classes.caption}>
            {result.caption ||
              t(result.status === "failed" ? "joblist.recent.faileddescription" : "joblist.recent.nocaption")}
          </Text>
          {result.truncated && (
            <Text size="xs" c="dimmed">
              {t("joblist.recent.truncated")}
            </Text>
          )}
        </Stack>
      </Group>
    </Paper>
  );
}

/** A fixed window, independent of the full-library count. */
export function RecentJobPhotos({ jobId, ownerId }: Readonly<{ jobId: number; ownerId: number }>) {
  const { t } = useTranslation();
  const { userId } = useAuth();
  const owned = userId === ownerId;
  const query = useRecentJobPhotosQuery(jobId, owned);
  const failure = useListFailure(query);
  if (!owned) return null;
  return (
    <Card shadow="md">
      <Stack>
        <Title order={4}>{t("joblist.recent.title")}</Title>
        <Text size="sm" c="dimmed">
          {t("joblist.recent.description", { count: query.data?.limit ?? 20 })}
        </Text>
        {query.isLoading && <PageLoader label={t("joblist.recent.loading")} />}
        {failure && <ErrorState failure={failure} compact />}
        {query.data?.results.length === 0 && (
          <EmptyState
            icon={<IconPhoto size={32} />}
            title={t("joblist.recent.empty")}
            description={t(query.data.finished ? "joblist.recent.emptyfinished" : "joblist.recent.emptydescription")}
          />
        )}
        {query.data?.results.map(result => (
          <ProcessedPhoto key={result.photo_id} result={result} />
        ))}
      </Stack>
    </Card>
  );
}
