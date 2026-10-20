import { endpoints, jobKeys, pollWhile } from "@librephotos/api-client";
import type { RecentJobPhotos } from "@librephotos/api-client";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../api";

/** The feed's completion flag keeps the last update from being missed by job polling. */
export const useRecentJobPhotosQuery = (id: number, enabled = true) =>
  useQuery({
    enabled,
    queryKey: jobKeys.recentPhotos(id),
    queryFn: () => endpoints.fetchRecentJobPhotos(apiClient, id),
    refetchInterval: pollWhile<RecentJobPhotos>(result => !result.finished, false),
  });
