"use client";
// NOTICE: Modified by LayerToll contributors for OKX Dev Day 2026. Original work: XPack MCP Marketplace (Apache-2.0).

import React from "react";
import MarkdownPreview from "@uiw/react-markdown-preview";
import { usePlatformConfig } from "@/shared/contexts/PlatformConfigContext";
import { Card, CardBody } from "@nextui-org/react";
import { useTranslation } from "@/shared/lib/useTranslation";

export const AboutContent: React.FC = () => {
  const { platformConfig } = usePlatformConfig();
  const { t } = useTranslation();

  return (
    <Card shadow="none" className="bg-transparent">
      <CardBody className="space-y-4">
        <h1 className="text-3xl font-bold mb-6">{t("About Us")}</h1>
        <div className="leading-relaxed max-w-none">
          {platformConfig.about_page ? (
            <MarkdownPreview source={platformConfig.about_page} />
          ) : (
            <MarkdownPreview
              source={`
**LayerToll** turns an existing business API into a paid AI-agent service.

- Import an OpenAPI spec — every operation becomes an MCP tool with a JSON input schema
- Choose which tools are free or paid and set a USD price per call
- Publish OKX AI A2MCP endpoints and an MCP endpoint for any agent
- Paid calls use HTTP 402 / x402 and settle in USDT0 on X Layer before the API runs
- Every call, payment and X Layer transaction hash shows up in the seller dashboard

LayerToll is built on the open-source [XPack MCP Marketplace](https://github.com/xpack-ai/XPack-MCP-Marketplace) (Apache-2.0).`}
            />
          )}
        </div>
      </CardBody>
    </Card>
  );
};
