"use client";
// NOTICE: Modified by LayerToll contributors for OKX Dev Day 2026. Original work: XPack MCP Marketplace (Apache-2.0).

import { useTranslation as useI18nTranslation } from "@/shared/lib/useTranslation";
import { usePlatformConfig } from "@/shared/contexts/PlatformConfigContext";

export const useTranslationWithPlatform = () => {
  const { t: originalT, ...rest } = useI18nTranslation();
  const { platformConfig } = usePlatformConfig();

  const t = (key: string, options?: any) => {
    const mergedOptions = {
      platformName: platformConfig.name || "LayerToll",
      ...options,
    };
    return originalT(key, mergedOptions);
  };

  return { t, ...rest };
};
