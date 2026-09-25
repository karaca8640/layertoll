// NOTICE: Modified by LayerToll contributors for OKX Dev Day 2026. Original work: XPack MCP Marketplace (Apache-2.0).
import { platformConfigService } from "@/services/platformConfigService";
import { PlatformConfig } from "@/shared/types/system";
import type { Metadata } from "next";
import { unstable_cache } from "next/cache";
import { headers } from "next/headers";

// use Next.js unstable_cache to cache with tags, bound to current host
export const getCachedPlatformConfig = async () => {
  const headersList = await headers();
  const host = headersList.get("host") || "default";

  const cachedFunction = unstable_cache(
    async () => {
      return await platformConfigService.getPlatformConfig();
    },
    [`platform-config-${host}`],
    {
      tags: [`platform-config-${host}`],
      revalidate: 300, // 5 minutes cache
    }
  );

  return await cachedFunction();
};

// get dynamic title
export const getDynamicTitle = async (pageTitle?: string) => {
  const platformConfig = await getCachedPlatformConfig();
  const websiteTitle =
    platformConfig.platform?.website_title ||
    platformConfig.platform?.headline ||
    platformConfig.platform?.name ||
    "LayerToll — sell your API to AI agents with x402 on X Layer";
  return {
    ...platformConfig.platform,
    website_title: pageTitle ? `${pageTitle} - ${websiteTitle}` : websiteTitle,
  } as PlatformConfig;
};

// create base metadata object
export const createBaseMetadata = (config: PlatformConfig): Metadata => {
  const url: string = `https://${config.domain || `${config.subdomain}${process.env.NEXT_PUBLIC_DOMAIN_HOST}`}`;
  return {
    title: config.website_title || config.headline,
    description:
      config?.meta_description ||
      config?.subheadline ||
      "unified platform simplifies API access, accelerates development, and unlocks a universe of capabilities for your AI agents, chatbots, and automated workflows. ",
    keywords: [
      "API integration platform",
      "Agent API connectivity",
      "AI agent integration",
      "Chatbot API access",
      "Automated workflow API",
      "Third-party API connector",
      "MCP connector",
      "MCP integration",
      "API management for agents",
      "Agent development platform",
      "API orchestration",
      "API gateway for agents",
      "No-code API integration",
      "Low-code API development",
      "Enterprise API connectivity",
      "Developer tools API",
      "x402",
      "X Layer",
      "OKX AI",
    ],
    authors: [{ name: "LayerToll contributors" }],
    openGraph: {
      siteName: config?.name,
      title: config?.x_title || config?.headline,
      description:
        config?.x_description ||
        config?.subheadline ||
        "Connect Your Agent to Any API/MCP",
      type: "website",
      images: [config?.facebook_image_url || "/static/publication-cover.png"],
      url: url,
    },
    twitter: {
      site: config?.name,
      title: config?.x_title || config?.headline,
      description:
        config?.x_description ||
        config?.subheadline ||
        "Connect Your Agent to Any API/MCP",
      images: [config?.x_image_url || "/static/publication-cover.png"],
      card: "summary_large_image",
    },
  };
};
