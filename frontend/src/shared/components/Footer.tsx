// NOTICE: Modified by LayerToll contributors for OKX Dev Day 2026. Original work: XPack MCP Marketplace (Apache-2.0).
'use client'
import React from "react";
import { usePlatformConfig } from "@/shared/contexts/PlatformConfigContext";
import { Link } from "@nextui-org/react";
interface FooterProps {
  showPoweredBy?: boolean;
}
export function Footer({ showPoweredBy=true }: FooterProps) {
  const { platformConfig } = usePlatformConfig();

  return (
    <footer className="py-4 px-4 sm:px-6 text-center sm:text-end max-w-7xl mx-auto text-xs">
      <span className="mr-1">© 2025 {platformConfig?.name}. All rights reserved.</span>
      {showPoweredBy && (
        <Link className="text-xs" href="https://github.com/xpack-ai/XPack-MCP-Marketplace">Built on XPack MCP Marketplace (Apache-2.0)</Link>
      )}
    </footer>
  );
}
