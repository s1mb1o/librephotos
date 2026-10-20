import { z } from "zod";
import { PageFields, UuidString } from "./common";

export const APIKeyPermission = z.enum(["photos:read", "metadata:write", "albums:write", "jobs:read", "jobs:submit"]);
export type APIKeyPermission = z.infer<typeof APIKeyPermission>;
export const APIKey = z.object({
  id: UuidString,
  name: z.string(),
  permissions: z.array(APIKeyPermission),
  created_at: z.string(),
  expires_at: z.string().nullable(),
  last_used_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
});
export type APIKey = z.infer<typeof APIKey>;
export const APIKeyCreated = APIKey.extend({ key: z.string() });
export type APIKeyCreated = z.infer<typeof APIKeyCreated>;
export const APIKeyPage = z.object({ ...PageFields, results: z.array(APIKey) });
export type APIKeyPage = z.infer<typeof APIKeyPage>;
export type APIKeyCreateRequest = {
  name: string;
  permissions: APIKeyPermission[];
  expires_at: string | null;
};
