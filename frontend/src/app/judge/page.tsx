import type { Metadata } from "next";
import JudgeMode from "@/components/judge/JudgeMode";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Judge mode · LayerToll",
  description: "Demo service, pricing, agent endpoints and x402 settlements on X Layer — live backend state.",
};

export default function JudgePage() {
  return <JudgeMode />;
}
