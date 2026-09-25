"use client";

// LayerToll (OKX Dev Day 2026): API -> paid agent service onboarding.
// Flow: Add API -> Configure tools -> Set pricing -> Publish -> Test agent call.
import React, { useState } from "react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Chip,
  Divider,
  Input,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  Select,
  SelectItem,
  Spinner,
  Switch,
  Tab,
  Tabs,
  Textarea,
} from "@nextui-org/react";
import { CheckCircle2, Copy, Plus, Rocket, Send, Upload } from "lucide-react";
import toast from "react-hot-toast";
import {
  AgentServiceDetail,
  AgentServiceSummary,
  AgentTool,
  TestCallResult,
  agentPayService,
  errorMessage,
} from "@/services/agentPayService";
import useSWR from "swr";

const STEPS = ["Add API", "Configure tools", "Set pricing", "Publish", "Test agent call"];

const copy = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    toast.success("Copied");
  } catch {
    toast.error("Copy failed");
  }
};

const exampleArgs = (tool: AgentTool) => {
  const args: Record<string, unknown> = {};
  const props = tool.input_schema?.properties || {};
  for (const name of tool.input_schema?.required || []) {
    const p = props[name] || {};
    args[name] = p.example ?? (p.type === "integer" || p.type === "number" ? 1 : p.type === "boolean" ? true : "");
  }
  return args;
};

const CopyLine: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex flex-col gap-1">
    <span className="text-tiny text-default-500">{label}</span>
    <div className="flex items-center gap-2">
      <code className="text-small bg-default-100 rounded px-2 py-1 break-all flex-1">{value}</code>
      <Button isIconOnly size="sm" variant="light" aria-label={`Copy ${label}`} onPress={() => copy(value)}>
        <Copy size={14} />
      </Button>
    </div>
  </div>
);

const Stepper: React.FC<{ current: number }> = ({ current }) => (
  <div className="flex flex-wrap gap-2 items-center">
    {STEPS.map((step, i) => (
      <React.Fragment key={step}>
        <Chip
          variant={i <= current ? "solid" : "bordered"}
          color={i < current ? "success" : i === current ? "primary" : "default"}
          startContent={i < current ? <CheckCircle2 size={14} /> : undefined}
        >
          {i + 1}. {step}
        </Chip>
        {i < STEPS.length - 1 && <span className="text-default-300">→</span>}
      </React.Fragment>
    ))}
  </div>
);

const AddApiModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  onImported: (svc: AgentServiceDetail) => void;
}> = ({ isOpen, onClose, onImported }) => {
  const [mode, setMode] = useState<string>("demo");
  const [url, setUrl] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const svc = await agentPayService.importApi({
        useDemo: mode === "demo",
        url: mode === "url" ? url.trim() : undefined,
        file: mode === "file" && file ? file : undefined,
        baseUrl: baseUrl.trim() || undefined,
      });
      toast.success(`Imported ${svc.tools.length} tools from ${svc.name}`);
      onImported(svc);
      onClose();
    } catch (e) {
      toast.error(errorMessage(e, "Import failed"));
    } finally {
      setBusy(false);
    }
  };

  const disabled = (mode === "url" && !url.trim()) || (mode === "file" && !file);

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl">
      <ModalContent>
        <ModalHeader>Add a business API</ModalHeader>
        <ModalBody>
          <p className="text-small text-default-500">
            Point LayerToll at an OpenAPI 3 spec. Every operation becomes an MCP tool with an input schema that
            agents can read.
          </p>
          <Tabs selectedKey={mode} onSelectionChange={(k) => setMode(String(k))} aria-label="Import source">
            <Tab key="demo" title="Demo API">
              <p className="text-small">
                Imports the bundled <b>Web Intelligence API</b> (URL analysis, summarization, entity extraction). It
                is a real API running next to the gateway and needs no API key. Suggested prices are prefilled:
                analyze_url 0.01 USD, extract_entities 0.005 USD, summarize_text free.
              </p>
            </Tab>
            <Tab key="url" title="OpenAPI URL">
              <Input
                label="OpenAPI URL (JSON or YAML)"
                placeholder="https://api.example.com/openapi.json"
                value={url}
                onValueChange={setUrl}
              />
            </Tab>
            <Tab key="file" title="Upload spec">
              <label className="flex items-center gap-2 cursor-pointer text-small">
                <Upload size={16} />
                <input
                  type="file"
                  accept=".json,.yaml,.yml,.txt"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </label>
            </Tab>
          </Tabs>
          <Input
            label="Business API base URL (optional)"
            description="Defaults to the spec's servers[0].url; editable later."
            placeholder="https://api.example.com"
            value={baseUrl}
            onValueChange={setBaseUrl}
          />
        </ModalBody>
        <ModalFooter>
          <Button variant="light" onPress={onClose}>
            Cancel
          </Button>
          <Button color="primary" isLoading={busy} isDisabled={disabled} onPress={submit}>
            Generate tools
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

const ToolRow: React.FC<{
  tool: AgentTool;
  price: string;
  enabled: boolean;
  onPrice: (v: string) => void;
  onEnabled: (v: boolean) => void;
}> = ({ tool, price, enabled, onPrice, onEnabled }) => {
  const params = Object.keys(tool.input_schema?.properties || {});
  const isPaid = !!price && Number(price) > 0;
  return (
    <div className="grid grid-cols-12 gap-3 items-center py-2 border-b border-divider last:border-0">
      <div className="col-span-1">
        <Switch size="sm" isSelected={enabled} onValueChange={onEnabled} aria-label={`Enable ${tool.name}`} />
      </div>
      <div className="col-span-5">
        <div className="font-medium">{tool.name}</div>
        <div className="text-tiny text-default-500 line-clamp-2">{tool.description}</div>
        <div className="text-tiny text-default-400 mt-1">
          {tool.method} {tool.path} · params: {params.length ? params.join(", ") : "none"}
        </div>
      </div>
      <div className="col-span-3">
        <Input
          size="sm"
          type="number"
          min="0"
          step="0.001"
          label="Price per call (USD)"
          placeholder="0 = free"
          value={price}
          onValueChange={onPrice}
        />
      </div>
      <div className="col-span-3 flex gap-2 flex-wrap">
        <Chip size="sm" color={isPaid ? "warning" : "success"} variant="flat">
          {isPaid ? `Paid · ${price} USDT0` : "Free"}
        </Chip>
        {isPaid && (
          <Chip size="sm" variant="flat">
            x402 · X Layer
          </Chip>
        )}
      </div>
    </div>
  );
};

const TestPanel: React.FC<{ service: AgentServiceDetail }> = ({ service }) => {
  const activeTools = service.tools.filter((t) => t.enabled);
  const argsFor = (name: string) => {
    const t = activeTools.find((x) => x.name === name);
    return t ? JSON.stringify(exampleArgs(t), null, 2) : "{}";
  };
  const [toolName, setToolName] = useState(activeTools[0]?.name || "");
  const [args, setArgs] = useState(() => argsFor(activeTools[0]?.name || ""));
  const [result, setResult] = useState<TestCallResult | null>(null);
  const [busy, setBusy] = useState(false);

  const selectTool = (name: string) => {
    setToolName(name);
    setArgs(argsFor(name));
    setResult(null);
  };

  const send = async () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(args || "{}");
    } catch {
      toast.error("Arguments must be valid JSON");
      return;
    }
    setBusy(true);
    try {
      setResult(await agentPayService.testCall(service.id, toolName, parsed));
    } catch (e) {
      toast.error(errorMessage(e, "Test failed"));
    } finally {
      setBusy(false);
    }
  };

  if (!service.published) {
    return <p className="text-small text-default-500">Publish the service to send a test request.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-small text-default-500">
        Sends a real request to the public A2MCP endpoint exactly as an agent would — without a payment. Free tools
        return the business result; paid tools return the HTTP 402 x402 challenge the agent must pay.
      </p>
      <div className="flex gap-3 items-end">
        <Select
          label="Tool"
          className="max-w-xs"
          selectedKeys={toolName ? [toolName] : []}
          onChange={(e) => selectTool(e.target.value)}
        >
          {activeTools.map((t) => (
            <SelectItem key={t.name}>{t.name}</SelectItem>
          ))}
        </Select>
        <Button color="primary" startContent={<Send size={16} />} isLoading={busy} onPress={send}>
          Send test request
        </Button>
      </div>
      <Textarea label="Arguments (JSON)" minRows={3} value={args} onValueChange={setArgs} className="font-mono" />
      {result && (
        <div className="flex flex-col gap-2">
          <div className="flex gap-2 items-center">
            <Chip color={result.status === 200 ? "success" : result.status === 402 ? "warning" : "danger"}>
              HTTP {result.status}
            </Chip>
            <code className="text-tiny break-all">
              {result.request.method} {result.request.url}
            </code>
          </div>
          {result.payment_required && (
            <Card shadow="none" className="border border-warning-200 bg-warning-50">
              <CardBody className="text-small">
                <b>402 Payment Required</b> — agent must pay {result.payment_required.accepts?.[0]?.amount} base units
                of {result.payment_required.accepts?.[0]?.asset} on {result.payment_required.accepts?.[0]?.network} to{" "}
                {result.payment_required.accepts?.[0]?.payTo}.
              </CardBody>
            </Card>
          )}
          <pre className="text-tiny bg-default-100 rounded p-3 overflow-auto max-h-80">
            {JSON.stringify(result.payment_required || result.body, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};

const ServiceEditor: React.FC<{ service: AgentServiceDetail; onChange: (s: AgentServiceDetail) => void }> = ({
  service,
  onChange,
}) => {
  // Form state is initialised from props; the parent remounts this editor (key)
  // whenever a fresh copy of the service is loaded.
  const [baseUrl, setBaseUrl] = useState(service.base_url || "");
  const [wallet, setWallet] = useState(service.payout_wallet || "");
  const [prices, setPrices] = useState<Record<string, string>>(() =>
    Object.fromEntries(service.tools.map((t) => [t.id, t.paid ? t.price_usd : ""]))
  );
  const [enabled, setEnabled] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(service.tools.map((t) => [t.id, t.enabled]))
  );
  const [saving, setSaving] = useState(false);

  const save = async (extra: Record<string, unknown> = {}) => {
    setSaving(true);
    try {
      const updated = await agentPayService.update(service.id, {
        base_url: baseUrl,
        payout_wallet: wallet,
        tools: service.tools.map((t) => ({ id: t.id, enabled: enabled[t.id], price_usd: prices[t.id] || "" })),
        ...extra,
      });
      onChange(updated);
      toast.success(extra.published === true ? "Published for agents" : "Saved");
    } catch (e) {
      toast.error(errorMessage(e, "Save failed"));
    } finally {
      setSaving(false);
    }
  };

  const paidCount = service.tools.filter((t) => t.enabled && t.paid).length;

  return (
    <div className="flex flex-col gap-4">
      <Card shadow="sm">
        <CardHeader className="flex justify-between">
          <div>
            <div className="text-lg font-semibold">{service.name}</div>
            <div className="text-small text-default-500">{service.description}</div>
          </div>
          <Chip color={service.published ? "success" : "default"} variant="flat">
            {service.published ? "Published to agents" : "Draft"}
          </Chip>
        </CardHeader>
        <CardBody className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input
            label="Business API base URL"
            value={baseUrl}
            onValueChange={setBaseUrl}
            description={service.has_upstream_headers ? "Upstream auth headers are stored server-side and never shown to agents." : undefined}
          />
          <Input
            label="X Layer payout wallet"
            placeholder="0x…"
            value={wallet}
            onValueChange={setWallet}
            description={
              !wallet && service.effective_payout_wallet
                ? `Using deployment default ${service.effective_payout_wallet}`
                : "Receives USDT0 from every paid call (x402 exact scheme)."
            }
          />
        </CardBody>
      </Card>

      <Card shadow="sm">
        <CardHeader className="flex justify-between">
          <div>
            <div className="font-semibold">Tools & pricing</div>
            <div className="text-tiny text-default-500">
              Generated from the OpenAPI spec. Leave the price empty for a free tool.
            </div>
          </div>
          <Button color="primary" variant="flat" isLoading={saving} onPress={() => save()}>
            Save
          </Button>
        </CardHeader>
        <CardBody>
          {service.tools.map((tool) => (
            <ToolRow
              key={tool.id}
              tool={tool}
              price={prices[tool.id] ?? ""}
              enabled={enabled[tool.id] ?? tool.enabled}
              onPrice={(v) => setPrices((p) => ({ ...p, [tool.id]: v }))}
              onEnabled={(v) => setEnabled((p) => ({ ...p, [tool.id]: v }))}
            />
          ))}
        </CardBody>
      </Card>

      <Card shadow="sm">
        <CardHeader className="flex justify-between">
          <div>
            <div className="font-semibold">Publish</div>
            <div className="text-tiny text-default-500">
              {paidCount} paid tool(s). Publishing exposes the endpoints below to any agent.
            </div>
          </div>
          <Button
            color={service.published ? "default" : "primary"}
            startContent={<Rocket size={16} />}
            isLoading={saving}
            onPress={() => save({ published: !service.published })}
          >
            {service.published ? "Unpublish" : "Publish"}
          </Button>
        </CardHeader>
        <CardBody className="flex flex-col gap-3">
          <CopyLine label="MCP endpoint (Streamable HTTP, x402 MCP transport)" value={service.endpoints.mcp} />
          <CopyLine label="A2MCP manifest" value={service.endpoints.manifest} />
          {service.tools
            .filter((t) => t.enabled)
            .map((t) => (
              <CopyLine key={t.id} label={`A2MCP endpoint · ${t.name}`} value={t.a2mcp_endpoint} />
            ))}
        </CardBody>
      </Card>

      <Card shadow="sm">
        <CardHeader>
          <div>
            <div className="font-semibold">OKX AI listing drafts (A2MCP)</div>
            <div className="text-tiny text-default-500">
              One A2MCP service per tool, in the four-line format OnchainOS validates. Register them with your own
              Agentic Wallet via OnchainOS; OKX AI reviews every listing. Requires a public HTTPS endpoint.
            </div>
          </div>
        </CardHeader>
        <CardBody className="flex flex-col gap-4">
          {service.tools
            .filter((t) => t.enabled)
            .map((t) => (
              <div key={t.id} className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <b>{t.okx_ai_listing.serviceName}</b>
                  <Chip size="sm" variant="flat">
                    fee {t.okx_ai_listing.fee}
                  </Chip>
                  {!t.okx_ai_listing.listingReady && (
                    <Chip size="sm" color="warning" variant="flat">
                      needs HTTPS endpoint
                    </Chip>
                  )}
                  <Button
                    size="sm"
                    variant="light"
                    startContent={<Copy size={14} />}
                    onPress={() => copy(JSON.stringify(t.okx_ai_listing, null, 2))}
                  >
                    Copy JSON
                  </Button>
                </div>
                <pre className="text-tiny bg-default-100 rounded p-2 whitespace-pre-wrap">
                  {t.okx_ai_listing.serviceDescription}
                </pre>
              </div>
            ))}
        </CardBody>
      </Card>

      <Card shadow="sm">
        <CardHeader className="font-semibold">Test agent call</CardHeader>
        <CardBody>
          <TestPanel key={`${service.id}-${service.published}`} service={service} />
        </CardBody>
      </Card>
    </div>
  );
};

export const AgentServices: React.FC = () => {
  const { data, error, mutate } = useSWR("agentpay:services", agentPayService.services);
  const services: AgentServiceSummary[] | null = data ?? (error ? [] : null);
  const load = () => mutate();
  const [selected, setSelected] = useState<AgentServiceDetail | null>(null);
  const [revision, setRevision] = useState(0);
  const [importOpen, setImportOpen] = useState(false);
  const select = (svc: AgentServiceDetail) => {
    setSelected(svc);
    setRevision((r) => r + 1);
  };

  const open = async (id: string) => {
    try {
      select(await agentPayService.service(id));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const step = !selected
    ? services && services.length
      ? 1
      : 0
    : selected.published
    ? 4
    : selected.tools.some((t) => t.paid)
    ? 3
    : 2;

  return (
    <div className="p-6 flex flex-col gap-5 h-full overflow-auto">
      <div className="flex justify-between items-start gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Agent Services</h1>
          <p className="text-default-500 text-small">
            Turn a business API into a paid service that OKX AI agents can discover, call and pay per request with
            x402 on X Layer.
          </p>
        </div>
        <Button color="primary" startContent={<Plus size={16} />} onPress={() => setImportOpen(true)}>
          Add API
        </Button>
      </div>
      <Stepper current={step} />
      <Divider />

      {error && <p className="text-danger text-small">{errorMessage(error, "Failed to load services")}</p>}
      {services === null ? (
        <Spinner />
      ) : services.length === 0 ? (
        <Card shadow="sm">
          <CardBody className="flex flex-col items-center gap-3 py-10 text-center">
            <p className="font-medium">No services yet</p>
            <p className="text-small text-default-500 max-w-lg">
              Import an OpenAPI spec, or start with the bundled Web Intelligence demo API to see the whole
              402 → pay → result flow.
            </p>
            <Button color="primary" onPress={() => setImportOpen(true)}>
              Add your first API
            </Button>
          </CardBody>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          <div className="flex flex-col gap-2 lg:col-span-1">
            {services.map((s) => (
              <Card
                key={s.id}
                isPressable
                shadow="sm"
                onPress={() => open(s.id)}
                className={selected?.id === s.id ? "border-2 border-primary" : ""}
              >
                <CardBody className="gap-1">
                  <div className="flex justify-between items-center gap-2">
                    <span className="font-medium truncate">{s.name}</span>
                    <Chip size="sm" color={s.published ? "success" : "default"} variant="flat">
                      {s.published ? "Published" : "Draft"}
                    </Chip>
                  </div>
                  <span className="text-tiny text-default-500">
                    {s.tools_active}/{s.tools_total} tools · {s.tools_paid} paid
                    {s.min_price_usd ? ` · from ${s.min_price_usd} USD` : ""}
                  </span>
                  <span className="text-tiny text-default-500">
                    {s.metrics.total_calls} calls · {s.metrics.paid_calls} paid · {s.metrics.revenue_usd} USD
                  </span>
                </CardBody>
              </Card>
            ))}
          </div>
          <div className="lg:col-span-3">
            {selected ? (
              <ServiceEditor
                key={`${selected.id}:${revision}`}
                service={selected}
                onChange={(s) => {
                  select(s);
                  load();
                }}
              />
            ) : (
              <p className="text-default-500 text-small">Select a service to configure tools, pricing and publishing.</p>
            )}
          </div>
        </div>
      )}

      <AddApiModal
        isOpen={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={(svc) => {
          select(svc);
          load();
        }}
      />
    </div>
  );
};

export default AgentServices;
