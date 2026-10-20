import { endpoints, type RemoteModelTestRequest } from "@librephotos/api-client";
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "../../api";
import { mutationErrorMeta } from "../../mutationErrors";

/** Test draft values. The form reports errors inline. No settings cache changes. */
export const useTestModelSettingsMutation = () =>
  useMutation({
    meta: mutationErrorMeta({ reportsErrors: true }),
    mutationFn: (input: RemoteModelTestRequest) => endpoints.testRemoteModel(apiClient, input),
  });
