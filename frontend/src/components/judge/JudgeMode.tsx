"use client";

// LayerToll (OKX Dev Day 2026): Judge mode — one screen, backend state only.
// No transaction, call or revenue shown here is simulated: everything comes from
// GET /api/agentpay/public/judge, and the buttons hit the real agent endpoints.
import React, { useState } from "react";
import useSWR from "swr";
import { Button, Card, CardBody, CardHeader, Chip, Divider, Link, Spinner } from "@nextui-org/react";
import { Play, RefreshCw } from "lucide-react";
import {
  ManifestTool,
  PaymentRequiredBody,
  TestPaymentResult,
  agentPayService,
  errorMessage,
  shortHash,
} from "@/services/agentPayService";
import { CallsTable } from "@/components/agent-services/SettlementDashboard";

type Probe = { label: string; status: number; headerDecoded?: PaymentRequiredBody; body: unknown } | null;

const decodeHeader = (value: string | null): PaymentRequiredBody | undefined => {
  if (!value) return undefined;
  try {
    const bytes = Uint8Array.from(atob(value), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return undefined;
  }
};

export const JudgeMode: React.FC = () => {
  const { data: view, error: loadError, mutate } = useSWR("agentpay:judge", agentPayService.judge);
  const error = loadError ? errorMessage(loadError, "Backend not reachable") : null;
  const load = () => mutate();
  const [probe, setProbe] = useState<Probe>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [testPay, setTestPay] = useState<TestPaymentResult | null>(null);
  const [testPayError, setTestPayError] = useState<string | null>(null);

  const runTestPayment = async (tool: ManifestTool) => {
    setBusy("testpay");
    setTestPayError(null);
    try {
      setTestPay(await agentPayService.testPayment(tool.name));
      load();
    } catch (e) {
      setTestPayError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const call = async (tool: ManifestTool, label: string) => {
    setBusy(label);
    try {
      const resp = await fetch(tool.a2mcpEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(tool.exampleArguments || {}),
      });
      const text = await resp.text();
      let body: unknown = text;
      try {
        body = JSON.parse(text);
      } catch {
        /* keep text */
      }
      setProbe({ label, status: resp.status, headerDecoded: decodeHeader(resp.headers.get("PAYMENT-REQUIRED")), body });
      load();
    } catch (e) {
      setProbe({ label, status: 0, body: { error: errorMessage(e) } });
    } finally {
      setBusy(null);
    }
  };

  if (error) {
    return <div className="p-8 text-danger">Judge data unavailable: {error}</div>;
  }
  if (!view) {
    return (
      <div className="p-8">
        <Spinner />
      </div>
    );
  }

  const net = view.network;
  const svc = view.service;
  const freeTool = svc?.tools.find((t) => !t.paid);
  const paidTool = svc?.tools.find((t) => t.paid);
  const settlement = view.latest_settlement;
  const testMode = net.payment_mode === "test";
  const testPayment = view.latest_test_payment;

  return (
    <div className="max-w-6xl mx-auto p-6 flex flex-col gap-5">
      <div className="flex justify-between items-start gap-4">
        <div>
          <h1 className="text-3xl font-bold">LayerToll · Judge mode</h1>
          <p className="text-default-500">
            A business API turned into a paid AI-agent service: OKX AI A2MCP + MCP endpoints, HTTP 402 / x402
            payments, settlement in USDT0 on X Layer. Everything below is live backend state of this deployment.
          </p>
        </div>
        <Button variant="flat" startContent={<RefreshCw size={16} />} onPress={load}>
          Refresh
        </Button>
      </div>

      {testMode && (
        <Card shadow="none" className="border-2 border-warning bg-warning-50">
          <CardBody className="text-small">
            <b>TEST ENVIRONMENT.</b> Payments on this public demo run in test mode on {net.network.name} (chain{" "}
            {net.network.chain_id}): the agent&apos;s x402 / EIP-3009 signature, amount, payee, expiry and replay are
            really verified, then the tool runs. Nothing is settled on chain, no funds move and no transaction hash
            exists. Revenue stays 0.
          </CardBody>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <Chip color={net.network.is_testnet ? "warning" : "primary"} variant="flat">
          {net.network.name} · chain {net.network.chain_id} · {net.network.caip2}
        </Chip>
        <Chip variant="flat">
          {net.network.payment_asset.symbol} {shortHash(net.network.payment_asset.address, 4)}
        </Chip>
        <Chip color={testMode ? "warning" : net.facilitator.configured ? "success" : "danger"} variant="flat">
          {testMode
            ? "x402: TEST MODE (verified, not settled)"
            : net.facilitator.configured
            ? "x402 facilitator: configured"
            : "x402 facilitator: NOT configured (paid calls fail closed)"}
        </Chip>
        <Chip variant="flat">OKX AI listing: pending (not submitted from this deployment)</Chip>
      </div>

      {!svc ? (
        <Card>
          <CardBody>No published service yet. Publish one from the admin console (Agent Services).</CardBody>
        </Card>
      ) : (
        <>
          <Card shadow="sm">
            <CardHeader className="flex flex-col items-start">
              <span className="text-tiny text-default-500">Demo service</span>
              <span className="text-xl font-semibold">{svc.service.name}</span>
              <span className="text-small text-default-500">{svc.service.description}</span>
            </CardHeader>
            <CardBody className="flex flex-col gap-2 text-small">
              <div>
                MCP endpoint: <code>{svc.endpoints.mcpStreamableHttp}</code>
              </div>
              <div>
                A2MCP manifest: <code>{svc.endpoints.a2mcpManifest}</code>
              </div>
              <Divider />
              <table className="w-full">
                <thead>
                  <tr className="text-left text-default-500">
                    <th className="py-1">Tool</th>
                    <th>Price</th>
                    <th>A2MCP endpoint</th>
                  </tr>
                </thead>
                <tbody>
                  {svc.tools.map((t) => (
                    <tr key={t.name}>
                      <td className="py-1 font-medium">{t.name}</td>
                      <td>
                        <Chip size="sm" variant="flat" color={t.paid ? "warning" : "success"}>
                          {t.paid ? `${t.priceUsd} USD · x402` : "free"}
                        </Chip>
                      </td>
                      <td>
                        <code className="text-tiny break-all">{t.a2mcpEndpoint}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardBody>
          </Card>

          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            {[
              ["Agent calls", view.metrics.total_calls],
              ["Successful", view.metrics.successful_calls],
              ["Paid (settled on chain)", view.metrics.paid_calls],
              ["Test-mode paid (not settled)", view.metrics.test_mode_paid_calls ?? 0],
              ["402 challenges", view.metrics.payment_challenges],
              ["Revenue", `${view.metrics.revenue_usd} USD`],
            ].map(([label, value]) => (
              <Card key={String(label)} shadow="sm">
                <CardBody>
                  <span className="text-tiny text-default-500">{label}</span>
                  <span className="text-xl font-semibold">{value}</span>
                </CardBody>
              </Card>
            ))}
          </div>

          <Card shadow="sm">
            <CardHeader className="font-semibold">Latest settlement</CardHeader>
            <CardBody className="text-small">
              {settlement ? (
                <div className="flex flex-col gap-1">
                  <span>
                    {settlement.tool_name} · {settlement.price_usd} USD · payer {shortHash(settlement.payer, 4)} → {" "}
                    {shortHash(settlement.pay_to, 4)}
                  </span>
                  <span>
                    X Layer tx:{" "}
                    {settlement.tx_url ? (
                      <Link href={settlement.tx_url} isExternal size="sm">
                        {settlement.tx_hash}
                      </Link>
                    ) : (
                      settlement.tx_hash
                    )}
                  </span>
                  <span>
                    RPC receipt check:{" "}
                    {settlement.onchain_verified === true
                      ? "Transfer confirmed on X Layer RPC"
                      : settlement.onchain_verified === false
                      ? "not confirmed"
                      : "not checked"}
                  </span>
                </div>
              ) : (
                <span className="text-default-500">
                  No on-chain settlement on this deployment.{" "}
                  {testMode
                    ? "It runs in test mode, so payments are verified but never settled."
                    : "Settling requires a funded X Layer wallet and a configured OKX facilitator."}
                </span>
              )}
              {testPayment && (
                <div className="flex flex-col gap-1 mt-3">
                  <Chip size="sm" color="warning" variant="flat">
                    Latest TEST payment: verified, not settled
                  </Chip>
                  <span>
                    {testPayment.tool_name} · {testPayment.price_usd} USD · payer {shortHash(testPayment.payer, 4)} →{" "}
                    {shortHash(testPayment.pay_to, 4)} · {testPayment.network} · tx: none (test mode)
                  </span>
                </div>
              )}
            </CardBody>
          </Card>

          <Card shadow="sm">
            <CardHeader className="font-semibold">Try the agent endpoints</CardHeader>
            <CardBody className="flex flex-col gap-3">
              <div className="flex gap-2 flex-wrap">
                {freeTool && (
                  <Button
                    startContent={<Play size={14} />}
                    isLoading={busy === "free"}
                    onPress={() => call(freeTool, "free")}
                  >
                    Call free tool ({freeTool.name})
                  </Button>
                )}
                {paidTool && (
                  <Button
                    color="warning"
                    startContent={<Play size={14} />}
                    isLoading={busy === "paid"}
                    onPress={() => call(paidTool, "paid")}
                  >
                    Call paid tool without payment ({paidTool.name})
                  </Button>
                )}
                {paidTool && testMode && (
                  <Button
                    color="primary"
                    startContent={<Play size={14} />}
                    isLoading={busy === "testpay"}
                    onPress={() => runTestPayment(paidTool)}
                  >
                    Pay in TEST MODE and call ({paidTool.name})
                  </Button>
                )}
              </div>
              {testPayError && <span className="text-danger text-small">{testPayError}</span>}
              {testPay && (
                <div className="flex flex-col gap-2 border border-divider rounded-lg p-3">
                  <span className="text-small font-semibold">
                    Test-mode agent run against {testPay.endpoint} (throw-away key, nothing settled)
                  </span>
                  {testPay.steps.map((s, i) => (
                    <div key={i} className="flex flex-col gap-1">
                      <div className="flex gap-2 items-center flex-wrap">
                        <Chip size="sm" variant="flat">
                          {i + 1}
                        </Chip>
                        <span className="text-small">{s.step}</span>
                        {s.status !== undefined && (
                          <Chip size="sm" color={s.status === 200 ? "success" : s.status === 402 ? "warning" : "danger"}>
                            HTTP {s.status}
                          </Chip>
                        )}
                      </div>
                      {s.payer && (
                        <code className="text-tiny break-all">
                          from {s.payer} to {s.to} · value {s.value} · {s.network}
                        </code>
                      )}
                      {s.payment_response && (
                        <code className="text-tiny break-all">
                          PAYMENT-RESPONSE: success={String(s.payment_response.success)} · status=
                          {s.payment_response.status} · transaction: none (test mode)
                        </code>
                      )}
                      {s.result !== undefined && (
                        <pre className="text-tiny bg-default-100 rounded p-2 overflow-auto max-h-56">
                          {JSON.stringify(s.result, null, 2)}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {probe && (
                <div className="flex flex-col gap-2">
                  <Chip color={probe.status === 200 ? "success" : probe.status === 402 ? "warning" : "danger"}>
                    HTTP {probe.status}
                  </Chip>
                  {probe.headerDecoded && (
                    <span className="text-small">
                      PAYMENT-REQUIRED header decoded: pay {probe.headerDecoded.accepts?.[0]?.amount} base units of{" "}
                      {shortHash(probe.headerDecoded.accepts?.[0]?.asset, 4)} on {probe.headerDecoded.accepts?.[0]?.network}{" "}
                      to {shortHash(probe.headerDecoded.accepts?.[0]?.payTo, 4)}
                    </span>
                  )}
                  <pre className="text-tiny bg-default-100 rounded p-3 overflow-auto max-h-72">
                    {JSON.stringify(probe.headerDecoded || probe.body, null, 2)}
                  </pre>
                </div>
              )}
            </CardBody>
          </Card>

          <Card shadow="sm">
            <CardHeader className="font-semibold">Latest agent calls</CardHeader>
            <CardBody>
              <CallsTable calls={view.latest_calls || []} empty="No activity yet." />
            </CardBody>
          </Card>
        </>
      )}

      <p className="text-tiny text-default-400">
        LayerToll is built on the open-source XPack MCP Marketplace (Apache-2.0). OKX, OKX AI and X Layer are
        trademarks of their respective owners; this project is an independent hackathon submission.
      </p>
    </div>
  );
};

export default JudgeMode;
