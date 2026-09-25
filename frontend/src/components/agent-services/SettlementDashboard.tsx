"use client";

// LayerToll (OKX Dev Day 2026): seller revenue, x402 receipts and endpoint health.
// Every number comes from the agent_call table; nothing is simulated.
import React from "react";
import useSWR from "swr";
import { Button, Card, CardBody, CardHeader, Chip, Link, Spinner, Tooltip } from "@nextui-org/react";
import { RefreshCw } from "lucide-react";
import { CallRecord, agentPayService, errorMessage, shortHash } from "@/services/agentPayService";

const STATUS_COLOR: Record<string, "success" | "warning" | "danger" | "default" | "primary"> = {
  settled: "success",
  test_verified: "warning",
  payment_required: "warning",
  rejected: "danger",
  settle_failed: "danger",
  verified: "default",
  not_required: "primary",
};

const STATUS_LABEL: Record<string, string> = {
  settled: "Settled",
  test_verified: "Test payment · not settled",
  payment_required: "402 issued",
  rejected: "Payment rejected",
  settle_failed: "Settlement failed",
  verified: "Verified · not charged",
  not_required: "Free",
};

const Metric: React.FC<{ label: string; value: React.ReactNode; hint?: string }> = ({ label, value, hint }) => (
  <Card shadow="sm">
    <CardBody className="gap-1">
      <span className="text-tiny text-default-500">{label}</span>
      <span className="text-2xl font-semibold">{value}</span>
      {hint && <span className="text-tiny text-default-400">{hint}</span>}
    </CardBody>
  </Card>
);

export const CallsTable: React.FC<{ calls: CallRecord[]; empty: string }> = ({ calls, empty }) =>
  calls.length === 0 ? (
    <p className="text-small text-default-500 py-4">{empty}</p>
  ) : (
    <div className="overflow-auto">
      <table className="w-full text-small">
        <thead>
          <tr className="text-left text-default-500 border-b border-divider">
            <th className="py-2 pr-3">Time (UTC)</th>
            <th className="pr-3">Tool</th>
            <th className="pr-3">Via</th>
            <th className="pr-3">Price</th>
            <th className="pr-3">Payment</th>
            <th className="pr-3">Payer</th>
            <th className="pr-3">X Layer tx</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((c) => (
            <tr key={c.id} className="border-b border-divider last:border-0">
              <td className="py-2 pr-3 whitespace-nowrap">{c.created_at?.replace("T", " ").slice(0, 19) || "—"}</td>
              <td className="pr-3">{c.tool_name}</td>
              <td className="pr-3">{c.transport === "mcp" ? "MCP" : "A2MCP"}</td>
              <td className="pr-3">{c.price_usd === "0" ? "free" : `${c.price_usd} USD`}</td>
              <td className="pr-3">
                <Tooltip content={c.payment_error || STATUS_LABEL[c.payment_status] || c.payment_status}>
                  <Chip size="sm" variant="flat" color={STATUS_COLOR[c.payment_status] || "default"}>
                    {STATUS_LABEL[c.payment_status] || c.payment_status}
                  </Chip>
                </Tooltip>
              </td>
              <td className="pr-3 font-mono text-tiny">{shortHash(c.payer, 4)}</td>
              <td className="pr-3 font-mono text-tiny">
                {c.tx_hash ? (
                  <span className="flex items-center gap-1">
                    {c.tx_url ? (
                      <Link href={c.tx_url} isExternal size="sm">
                        {shortHash(c.tx_hash)}
                      </Link>
                    ) : (
                      shortHash(c.tx_hash)
                    )}
                    {c.onchain_verified === true && (
                      <Chip size="sm" color="success" variant="dot">
                        RPC-confirmed
                      </Chip>
                    )}
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td>
                {c.success ? (
                  <Chip size="sm" color="success" variant="flat">
                    {c.latency_ms != null ? `ok · ${c.latency_ms} ms` : "ok"}
                  </Chip>
                ) : (
                  <Chip size="sm" variant="flat">
                    {c.upstream_status ? `upstream ${c.upstream_status}` : "not executed"}
                  </Chip>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

export const SettlementDashboard: React.FC = () => {
  const { data, error, isValidating, mutate } = useSWR("agentpay:dashboard", agentPayService.dashboard);
  const loading = isValidating;
  const load = () => mutate();

  if (error && !data) {
    return <div className="p-6 text-danger">{errorMessage(error, "Failed to load dashboard")}</div>;
  }
  if (!data) {
    return (
      <div className="p-6">
        <Spinner />
      </div>
    );
  }
  const m = data.metrics;
  const net = data.network;

  return (
    <div className="p-6 flex flex-col gap-5 h-full overflow-auto">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-semibold">Settlement</h1>
          <p className="text-small text-default-500">
            Agent calls, x402 payments and receipts on {net.network.name} (chain {net.network.chain_id}).
          </p>
        </div>
        <Button variant="flat" startContent={<RefreshCw size={16} />} isLoading={loading} onPress={load}>
          Refresh
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        <Chip variant="flat" color={net.network.is_testnet ? "warning" : "primary"}>
          {net.network.name} · {net.network.caip2}
        </Chip>
        <Chip variant="flat">
          Asset {net.network.payment_asset.symbol} {shortHash(net.network.payment_asset.address, 4)}
        </Chip>
        <Chip
          variant="flat"
          color={net.payment_mode === "test" ? "warning" : net.facilitator.configured ? "success" : "danger"}
        >
          {net.payment_mode === "test"
            ? "TEST MODE: payments verified, never settled on chain"
            : net.facilitator.configured
            ? "OKX x402 facilitator configured"
            : "Facilitator not configured — paid calls are rejected"}
        </Chip>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <Metric label="Agent calls" value={m.total_calls} hint="incl. 402 challenges" />
        <Metric label="Successful calls" value={m.successful_calls} />
        <Metric label="Paid calls (settled)" value={m.paid_calls} />
        {net.payment_mode === "test" && (
          <Metric label="Test-mode paid calls" value={m.test_mode_paid_calls} hint="verified, not settled" />
        )}
        <Metric label="Revenue" value={`${m.revenue_usd} USD`} hint={`settled in ${net.network.payment_asset.symbol}`} />
        <Metric label="402 challenges" value={m.payment_challenges} />
        <Metric label="Rejected payments" value={m.rejected_payments} hint="invalid / reused proofs" />
      </div>

      <Card shadow="sm">
        <CardHeader className="font-semibold">Services</CardHeader>
        <CardBody>
          {data.services.length === 0 ? (
            <p className="text-small text-default-500">No activity yet — add an API under Agent Services.</p>
          ) : (
            <table className="w-full text-small">
              <thead>
                <tr className="text-left text-default-500 border-b border-divider">
                  <th className="py-2">Service</th>
                  <th>Status</th>
                  <th>Tools</th>
                  <th>Price range</th>
                  <th>Calls</th>
                  <th>Revenue</th>
                  <th>Endpoint health</th>
                </tr>
              </thead>
              <tbody>
                {data.services.map((s) => (
                  <tr key={s.id} className="border-b border-divider last:border-0">
                    <td className="py-2">{s.name}</td>
                    <td>
                      <Chip size="sm" variant="flat" color={s.published ? "success" : "default"}>
                        {s.published ? "Published" : "Draft"}
                      </Chip>
                    </td>
                    <td>
                      {s.tools_active} active · {s.tools_paid} paid
                    </td>
                    <td>
                      {s.min_price_usd
                        ? s.min_price_usd === s.max_price_usd
                          ? `${s.min_price_usd} USD`
                          : `${s.min_price_usd}–${s.max_price_usd} USD`
                        : "free"}
                    </td>
                    <td>
                      {s.metrics.total_calls} ({s.metrics.paid_calls} paid)
                    </td>
                    <td>{s.metrics.revenue_usd} USD</td>
                    <td>
                      <Chip
                        size="sm"
                        variant="dot"
                        color={s.health?.status === "reachable" ? "success" : s.health?.status === "not_configured" ? "default" : "danger"}
                      >
                        {s.health?.status || "unknown"}
                        {s.health?.http_status ? ` · ${s.health.http_status}` : ""}
                      </Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>

      <Card shadow="sm">
        <CardHeader className="font-semibold">Latest x402 receipts</CardHeader>
        <CardBody>
          <CallsTable calls={data.latest_receipts} empty="No settled payments yet." />
        </CardBody>
      </Card>

      <Card shadow="sm">
        <CardHeader className="font-semibold">Latest agent calls</CardHeader>
        <CardBody>
          <CallsTable calls={data.latest_calls} empty="No activity yet." />
        </CardBody>
      </Card>
    </div>
  );
};

export default SettlementDashboard;
