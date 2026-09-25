// LayerToll (OKX Dev Day 2026): client for /api/agentpay admin + public endpoints.
import { fetchAdminAPI } from "@/rpc/admin-api";
import { getApiUrl } from "@/shared/rpc/adapter";
import { ApiResponse } from "@/shared/types";

export interface PaymentTerms {
  protocol: string;
  x402Version: number;
  scheme: string;
  network: string;
  asset: string;
  assetSymbol: string;
  priceUsd: string;
  amountAtomic: string;
  payTo: string | null;
}

export interface OkxAiListing {
  serviceType: "A2MCP";
  serviceName: string;
  serviceDescription: string;
  fee: string;
  endpoint: string;
  listingReady: boolean;
  status: string;
}

export interface AgentTool {
  id: string;
  name: string;
  description: string;
  method: string;
  path: string;
  enabled: boolean;
  price_usd: string;
  paid: boolean;
  input_schema: {
    type: string;
    properties: Record<string, { type?: string; description?: string; example?: unknown }>;
    required: string[];
  };
  a2mcp_endpoint: string;
  payment: PaymentTerms | null;
  okx_ai_listing: OkxAiListing;
}

export interface AgentServiceDetail {
  id: string;
  name: string;
  slug: string;
  description: string;
  base_url: string | null;
  has_upstream_headers: boolean;
  enabled: boolean;
  published: boolean;
  payout_wallet: string | null;
  effective_payout_wallet: string | null;
  endpoints: { mcp: string; manifest: string };
  tools: AgentTool[];
}

export interface Metrics {
  total_calls: number;
  successful_calls: number;
  paid_calls: number;
  payment_challenges: number;
  rejected_payments: number;
  revenue_usd: string;
}

export interface AgentServiceSummary {
  id: string;
  name: string;
  slug: string;
  enabled: boolean;
  published: boolean;
  payout_wallet: string | null;
  tools_total: number;
  tools_active: number;
  tools_paid: number;
  min_price_usd: string | null;
  max_price_usd: string | null;
  metrics: Metrics;
  health?: { status: string; http_status?: number };
}

export interface CallRecord {
  id: string;
  created_at: string | null;
  service_id: string;
  tool_name: string;
  transport: string;
  price_usd: string;
  payment_status: string;
  payment_error: string | null;
  payer: string | null;
  pay_to: string | null;
  network: string | null;
  tx_hash: string | null;
  tx_url: string | null;
  onchain_verified: boolean | null;
  success: boolean;
  upstream_status: number | null;
  latency_ms: number | null;
}

export interface NetworkStatus {
  network: {
    key: string;
    name: string;
    chain_id: number;
    caip2: string;
    rpc_url: string;
    explorer_url: string;
    native_gas_token: string;
    is_testnet: boolean;
    payment_asset: { symbol: string; address: string; decimals: number };
  };
  facilitator: { provider: string; base_url: string; configured: boolean };
  onchain_receipt_check: boolean;
  public_base_url: string;
  default_payout_wallet: string | null;
}

export interface Dashboard {
  metrics: Metrics;
  services: AgentServiceSummary[];
  latest_calls: CallRecord[];
  latest_receipts: CallRecord[];
  network: NetworkStatus;
}

export interface PaymentRequirement {
  scheme: string;
  network: string;
  asset: string;
  amount: string;
  payTo: string;
  maxTimeoutSeconds: number;
  extra?: Record<string, unknown>;
}

export interface PaymentRequiredBody {
  x402Version: number;
  error?: string;
  resource?: { url: string; description?: string; mimeType?: string };
  accepts: PaymentRequirement[];
}

export interface TestCallResult {
  request: { method: string; url: string; json: Record<string, unknown> };
  status: number;
  payment_required: PaymentRequiredBody | null;
  body: unknown;
}

export interface ManifestTool {
  name: string;
  description: string;
  paid: boolean;
  priceUsd: string;
  a2mcpEndpoint: string;
  exampleArguments: Record<string, unknown>;
  payment: PaymentTerms | null;
  okxAiListing: OkxAiListing;
}

export interface ServiceManifest {
  service: { id: string; slug: string; name: string; description: string };
  endpoints: { mcpStreamableHttp: string; a2mcpManifest: string };
  tools: ManifestTool[];
}

export interface JudgeView {
  service: ServiceManifest | null;
  network: NetworkStatus;
  metrics: Metrics;
  latest_settlement?: CallRecord | null;
  latest_calls?: CallRecord[];
}

async function unwrap<T>(promise: Promise<ApiResponse<T>>): Promise<T> {
  const res = await promise;
  if (!res.success) {
    throw new Error(res.error_message || "Request failed");
  }
  return res.data;
}

export const agentPayService = {
  network: () => unwrap<NetworkStatus>(fetchAdminAPI("/api/agentpay/network")),
  dashboard: () => unwrap<Dashboard>(fetchAdminAPI("/api/agentpay/dashboard")),
  services: () => unwrap<AgentServiceSummary[]>(fetchAdminAPI("/api/agentpay/services")),
  service: (id: string) => unwrap<AgentServiceDetail>(fetchAdminAPI(`/api/agentpay/services/${id}`)),
  update: (id: string, body: Record<string, unknown>) =>
    unwrap<AgentServiceDetail>(
      fetchAdminAPI(`/api/agentpay/services/${id}`, { method: "PUT", body: JSON.stringify(body) })
    ),
  importApi: (opts: { url?: string; file?: File; useDemo?: boolean; baseUrl?: string }) => {
    const form = new FormData();
    if (opts.url) form.append("url", opts.url);
    if (opts.file) form.append("file", opts.file);
    if (opts.useDemo) form.append("use_demo", "true");
    if (opts.baseUrl) form.append("base_url", opts.baseUrl);
    return unwrap<AgentServiceDetail>(fetchAdminAPI("/api/agentpay/import", { method: "POST", body: form }));
  },
  testCall: (id: string, tool: string, args: Record<string, unknown>) =>
    unwrap<TestCallResult>(
      fetchAdminAPI(`/api/agentpay/services/${id}/test`, {
        method: "POST",
        body: JSON.stringify({ tool, arguments: args }),
      })
    ),
  judge: async (): Promise<JudgeView> => {
    const res = await fetch(getApiUrl("/api/agentpay/public/judge"), { cache: "no-store" });
    const json = await res.json();
    if (!json.success) throw new Error(json.error_message || "Request failed");
    return json.data;
  },
};

export const shortHash = (value?: string | null, size = 6) =>
  value ? `${value.slice(0, size + 2)}…${value.slice(-size)}` : "—";

export const errorMessage = (e: unknown, fallback = "Request failed") =>
  e instanceof Error && e.message ? e.message : fallback;
