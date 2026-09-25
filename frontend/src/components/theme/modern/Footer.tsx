"use client";
// NOTICE: Modified by LayerToll contributors for OKX Dev Day 2026. Original work: XPack MCP Marketplace (Apache-2.0).

import { Sparkles } from "lucide-react";
import React from "react";
import { usePlatformConfig } from "@/shared/contexts/PlatformConfigContext";

interface FooterProps {}

export const Footer: React.FC<FooterProps> = ({}) => {
  const { platformConfig } = usePlatformConfig();
  return (
    <>
      {/* Modern Footer */}
      <footer className="relative z-10">
        <div className="bg-gradient-to-r from-slate-800 via-gray-800 to-slate-900">
          <div className="mx-auto px-6 py-2 max-w-7xl">
            <div className=" flex justify-between items-center gap-2">
              <span className="text-gray-300 text-sm">
                © 2025 {platformConfig?.name}. All rights reserved.
              </span>

              <a
                href="https://github.com/xpack-ai/XPack-MCP-Marketplace"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-primary-400 text-xs"
              >
                <span>Built on XPack MCP Marketplace (Apache-2.0)</span>
              </a>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
};
