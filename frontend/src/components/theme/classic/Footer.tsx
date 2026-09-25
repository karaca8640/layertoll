"use client";
// NOTICE: Modified by LayerToll contributors for OKX Dev Day 2026. Original work: XPack MCP Marketplace (Apache-2.0).

import React from "react";
import { usePlatformConfig } from "@/shared/contexts/PlatformConfigContext";
import Link from "next/link";

interface FooterProps {}

export const Footer: React.FC<FooterProps> = ({}) => {
  const { platformConfig } = usePlatformConfig();
  return (
    <>
      {/* Classic Footer */}
      <footer className="bg-slate-700 text-white py-1">
        <div className="mx-auto px-6 max-w-7xl">
          <div className="text-center">
            <span className="text-gray-300 text-xs mr-2">
              © 2025 {platformConfig?.name}
            </span>

            <Link
              className="text-xs text-primary-500 hover:text-primary-600 transition-colors"
              href="https://github.com/xpack-ai/XPack-MCP-Marketplace"
            >
              Built on XPack MCP Marketplace (Apache-2.0)
            </Link>
          </div>
        </div>
      </footer>
    </>
  );
};
