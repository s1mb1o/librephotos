import { apiKeyKeys, endpoints } from "@librephotos/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../../api";

export function useApiKeys(page: number) {
  return useQuery({ queryKey: apiKeyKeys.page(page), queryFn: () => endpoints.fetchAPIKeys(apiClient, page) });
}

export function useCreateApiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (values: Parameters<typeof endpoints.createAPIKey>[1]) => endpoints.createAPIKey(apiClient, values),
    gcTime: 0,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: apiKeyKeys.all });
    },
  });
}

export function useRevokeApiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => endpoints.revokeAPIKey(apiClient, id),
    onSuccess: () => client.invalidateQueries({ queryKey: apiKeyKeys.all }),
  });
}
