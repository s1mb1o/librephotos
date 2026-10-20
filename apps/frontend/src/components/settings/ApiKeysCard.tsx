import { APIKeyPermission, type APIKey, type APIKeyPermission as Permission } from "@librephotos/api-client";
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Code,
  Group,
  Modal,
  Pagination,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import type { ParseKeys } from "i18next";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "../../api_client/auth/hooks/useApiKeys";
import { fromPickerValue, parseInstant } from "../../util/dateUtils";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { PageLoader } from "../common/PageLoader";
import { useListFailure } from "../common/useListFailure";
import { SectionLink } from "./SettingsSection";

const LABELS: Record<Permission, ParseKeys> = {
  "photos:read": "settings.apiKeys.photosRead",
  "metadata:write": "settings.apiKeys.metadataWrite",
  "albums:write": "settings.apiKeys.albumsWrite",
  "jobs:read": "settings.apiKeys.jobsRead",
  "jobs:submit": "settings.apiKeys.jobsSubmit",
};

function KeyRow({ item, onRevoke, pending }: { item: APIKey; onRevoke: () => void; pending: boolean }) {
  const { t } = useTranslation();
  const time = (value: string | null) => (value ? parseInstant(value).toLocaleString() : t("settings.apiKeys.never"));
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group justify="space-between">
          <Text fw={600}>{item.name}</Text>
          {item.revoked_at ? (
            <Badge color="gray">{t("settings.apiKeys.revoked")}</Badge>
          ) : (
            <Button color="red" variant="light" loading={pending} onClick={onRevoke}>
              {t("settings.apiKeys.revoke")}
            </Button>
          )}
        </Group>
        <Code>{item.id}</Code>
        <Text size="sm">{item.permissions.map(value => t(LABELS[value])).join(", ")}</Text>
        <Text size="sm">
          {t("settings.apiKeys.created")}: {time(item.created_at)}
        </Text>
        <Text size="sm">
          {t("settings.apiKeys.expires")}: {time(item.expires_at)}
        </Text>
        <Text size="sm">
          {t("settings.apiKeys.lastUsed")}: {time(item.last_used_at)}
        </Text>
      </Stack>
    </Card>
  );
}

export function ApiKeysCard() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const query = useApiKeys(page);
  const failure = useListFailure(query);
  const create = useCreateApiKey();
  const revoke = useRevokeApiKey();
  const [name, setName] = useState("");
  const [permissions, setPermissions] = useState<Permission[]>(["photos:read", "jobs:read"]);
  const [expiration, setExpiration] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [revokeId, setRevokeId] = useState<string | null>(null);
  const closeSecret = () => {
    setSecret(null);
    create.reset();
  };
  return (
    <Card shadow="md">
      <Stack>
        <Title order={4}>
          {t("settings.apiKeys.title")}
          <SectionLink />
        </Title>
        <Text size="sm" c="dimmed">
          {t("settings.apiKeys.description")}
        </Text>
        <TextInput
          label={t("settings.apiKeys.name")}
          value={name}
          onChange={event => setName(event.currentTarget.value)}
          maxLength={128}
        />
        <Checkbox.Group
          label={t("settings.apiKeys.permissions")}
          value={permissions}
          onChange={values => setPermissions(values.map(value => APIKeyPermission.parse(value)))}
        >
          <Stack gap="xs" mt="xs">
            {APIKeyPermission.options.map(value => (
              <Checkbox key={value} value={value} label={t(LABELS[value])} />
            ))}
          </Stack>
        </Checkbox.Group>
        <DateTimePicker
          clearable
          label={t("settings.apiKeys.expires")}
          description={t("settings.apiKeys.noExpiration")}
          value={expiration}
          onChange={setExpiration}
        />
        <Button
          loading={create.isPending}
          onClick={() => {
            if (!name.trim() || permissions.length === 0) return;
            create.mutate(
              { name: name.trim(), permissions, expires_at: expiration ? fromPickerValue(expiration) : null },
              {
                onSuccess: data => {
                  setSecret(data.key);
                  setName("");
                  create.reset();
                },
              }
            );
          }}
        >
          {t("settings.apiKeys.create")}
        </Button>
        {query.isPending && <PageLoader />}
        {failure && <ErrorState compact failure={failure} />}
        {query.data?.results.map(item => (
          <KeyRow
            key={item.id}
            item={item}
            pending={revoke.isPending && revoke.variables === item.id}
            onRevoke={() => setRevokeId(item.id)}
          />
        ))}
        {query.data?.count === 0 && (
          <EmptyState title={t("settings.apiKeys.empty")} description={t("settings.apiKeys.noExpiration")} />
        )}
        {(query.data?.num_pages ?? 1) > 1 && (
          <Pagination value={page} onChange={setPage} total={query.data?.num_pages ?? 1} />
        )}
      </Stack>
      <Modal opened={secret !== null} onClose={closeSecret} title={t("settings.apiKeys.copyTitle")}>
        <Stack>
          <Alert>{t("settings.apiKeys.copyOnce")}</Alert>
          <TextInput
            readOnly
            aria-label={t("settings.apiKeys.secret")}
            value={secret ?? ""}
            onFocus={event => event.currentTarget.select()}
          />
          <Button onClick={closeSecret}>{t("settings.apiKeys.done")}</Button>
        </Stack>
      </Modal>
      <Modal opened={revokeId !== null} onClose={() => setRevokeId(null)} title={t("settings.apiKeys.revoke")}>
        <Stack>
          <Text>{t("settings.apiKeys.confirmRevoke")}</Text>
          <Button
            color="red"
            loading={revoke.isPending}
            onClick={() => {
              if (revokeId) revoke.mutate(revokeId, { onSuccess: () => setRevokeId(null) });
            }}
          >
            {t("settings.apiKeys.revoke")}
          </Button>
        </Stack>
      </Modal>
    </Card>
  );
}
