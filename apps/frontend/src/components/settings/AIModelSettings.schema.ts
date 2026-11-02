import type { TFunction } from "i18next";
import { z } from "zod";

export function makeAIModelSettingsSchema(t: TFunction) {
  return z
    .object({
      provider: z.string(),
      url: z.string(),
      model_name: z.string(),
      token: z.string(),
      clear_token: z.boolean(),
      disable_thinking: z.boolean(),
      revision: z.string(),
      max_num_patches: z.union([z.number(), z.string()]),
      search_threshold: z.union([z.number(), z.string()]),
      similar_threshold: z.union([z.number(), z.string()]),
      tag_threshold: z.union([z.number(), z.string()]),
    })
    .superRefine((values, context) => {
      if (values.provider !== "openai_api" && values.provider !== "siglip2_naflex") return;
      if (values.provider === "siglip2_naflex") {
        const patches = values.max_num_patches;
        if (typeof patches !== "number" || !Number.isInteger(patches) || patches < 1 || patches > 4096)
          context.addIssue({
            code: "custom",
            path: ["max_num_patches"],
            message: t("aimodelsettings.patches_invalid"),
          });
        for (const key of ["search_threshold", "similar_threshold", "tag_threshold"] as const) {
          const threshold = values[key];
          if (typeof threshold !== "number" || !Number.isFinite(threshold) || threshold < -1 || threshold > 1)
            context.addIssue({ code: "custom", path: [key], message: t("aimodelsettings.threshold_invalid") });
        }
      }
      let validUrl: boolean;
      try {
        const url = new URL(values.url);
        validUrl =
          ["http:", "https:"].includes(url.protocol) && !url.username && !url.password && !url.search && !url.hash;
      } catch {
        validUrl = false;
      }
      if (!validUrl) context.addIssue({ code: "custom", path: ["url"], message: t("aimodelsettings.invalid_url") });
      if (!values.model_name.trim())
        context.addIssue({ code: "custom", path: ["model_name"], message: t("aimodelsettings.model_required") });
    });
}
