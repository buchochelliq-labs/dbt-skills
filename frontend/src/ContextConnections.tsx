import React, { useState } from "react";
import { useDraftGuard, useNavigationGuard } from "./draftGuard";
import "./connections-graph.css";
import {
  ArrowUp,
  ArrowDown,
  Clock,
  Download,
  Sparkle,
  Plus,
} from "@phosphor-icons/react";
import { useRepo } from "./store";
import { knowledgeView, ttl, recommendation } from "./services";
import type { ResolutionOutcome, Provider } from "./contracts";
import {
  Panel,
  Title,
  Button,
  Status,
  TextInput,
  Select,
  opts,
  Json,
  StateNotice,
  KeyValue,
  Callout,
  downloadJSON,
  Tabs,
  Modal,
} from "./components";
export function AgentPreview({ objectId }: { objectId?: string }) {
  const { state, reader, setReader, command, simulation } = useRepo();
  const attempt = useNavigationGuard();
  const object = state.knowledge.find((k) => k.id === objectId);
  const [question, setQuestion] = useState(
      object?.name || (simulation ? "Active customer" : ""),
    ),
    [scope, setScope] = useState("Unspecified"),
    [selected, setSelected] = useState(objectId || ""),
    [result, setResult] = useState<ResolutionOutcome | null>(null),
    [mode, setMode] = useState("Readable"),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState("");
  const stale =
    result &&
    revision !==
      `${state.configVersion}:${state.clock}:${reader}:${question}:${scope}:${selected}`;
  async function run() {
    setBusy(true);
    try {
      const r = await command<ResolutionOutcome>("context.resolve", {
        request: { question, scope, reader, objectId: selected || undefined },
      });
      if (r) {
        setResult(r);
        setRevision(
          `${state.configVersion}:${state.clock}:${reader}:${question}:${scope}:${selected}`,
        );
      }
    } finally {
      setBusy(false);
    }
  }
  const clear = () => setResult(null);
  return (
    <div className="context-studio">
      <Callout>
        {simulation
          ? "Deterministic fixture resolver. No LLM calls, queries or source records."
          : "Server-resolved metadata context. No source queries are executed."}
      </Callout>
      <TextInput
        label="Question"
        value={question}
        onChange={(v) => {
          setQuestion(v);
          setSelected("");
          clear();
        }}
      />
      <div className="form-grid">
        <Select
          label="Selected definition (optional)"
          value={selected}
          onChange={(v) => {
            setSelected(v);
            clear();
          }}
          options={[
            { value: "", label: "Resolve by question" },
            ...knowledgeView(state, reader).map((k) => ({
              value: k.id,
              label: `${k.name} · ${k.scope}`,
            })),
          ]}
        />
        <Select
          label="Business scope"
          value={scope}
          onChange={(v) => {
            setScope(v);
            clear();
          }}
          options={opts([
            "Unspecified",
            ...new Set(
              knowledgeView(state, reader)
                .map((k) =>
                  simulation && k.scope === "Collections" ? "Billing" : k.scope,
                )
                .filter((scope) => scope && scope !== "Unspecified"),
            ),
          ])}
        />
        <Select
          label={simulation ? "Simulated reader" : "Reader"}
          value={reader}
          onChange={(v) => attempt(() => {
            void setReader(v as any);
            clear();
          })}
          options={[
            { value: "steward", label: "Steward · permitted metadata" },
            { value: "restricted", label: "Restricted · no Finance facts" },
          ]}
        />
      </div>
      <Button variant="primary" icon={Sparkle} onClick={run} disabled={busy}>
        {busy ? "Resolving context…" : "Resolve context"}
      </Button>
      {busy && <StateNotice title="Loading permitted context" />}
      {result && (
        <>
          <div className="result-heading">
            <Status value={result.state} />
            <span>{result.message}</span>
          </div>
          {stale && (
            <StateNotice
              title="Configuration changed — refresh context"
              kind="stale"
            >
              Export is disabled until you resolve again.
            </StateNotice>
          )}
          <Tabs items={["Readable", "JSON"]} value={mode} onChange={setMode} />
          {mode === "JSON" ? (
            <Json value={result} />
          ) : (
            <>
              {result.choices?.map((c) => (
                <Button
                  key={c.id}
                  onClick={() => {
                    setScope(c.scope);
                    setSelected(c.id);
                    clear();
                  }}
                >
                  {c.scope} meaning
                </Button>
              ))}
              {result.facts.map((f) => (
                <Panel key={f.id} title={f.id}>
                  <p>{f.value}</p>
                  <details>
                    <summary>
                      Evidence · {f.evidence.providerId} · revision{" "}
                      {f.evidence.originRevision}
                    </summary>
                    <KeyValue
                      items={{
                        "Semantic origin": f.evidence.originId,
                        "Source path": f.evidence.sourcePath,
                        Provider: f.evidence.providerId,
                        "Source asset": f.evidence.assetId,
                        "Observed at": new Date(
                          f.evidence.observedAt,
                        ).toISOString(),
                        Approval: f.evidence.approval,
                        Origin: f.evidence.origin,
                        Confidence: f.evidence.confidence,
                        Authority: f.evidence.authority,
                        Replica: f.evidence.replica
                          ? "Explicit replica; same origin"
                          : "Origin evidence",
                        Reader: f.evidence.reader,
                        "Policy version": f.evidence.policyVersion,
                      }}
                    />
                  </details>
                </Panel>
              ))}
            </>
          )}
          <details className="trace" open>
            <summary>Resolution trace</summary>
            <ol>
              {result.trace.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ol>
          </details>
          <Button
            icon={Download}
            disabled={!!stale}
            onClick={() => downloadJSON(result, "uol-agent-context.json")}
          >
            Export context JSON
          </Button>
        </>
      )}
    </div>
  );
}
export function Connections() {
  const { state, command, simulation } = useRepo();
  const [edit, setEdit] = useState<string | null>(null),
    [adding, setAdding] = useState(false),
    [ttlEdit, setTtlEdit] = useState(""),
    [recEdit, setRecEdit] = useState(false);
  const rec = recommendation(state);
  const p = state.providers.find((p) => p.id === edit);
  return (
    <div className="screen-pad">
      <Title
        eyebrow="Connections"
        title="Context, from the right source."
        description="Order metadata reads independently from native delivery destinations."
        action={
          <Button
            icon={Plus}
            disabled={!simulation}
            onClick={() => setAdding(true)}
          >
            Add provider
          </Button>
        }
      />
      {!simulation && (
        <Callout>
          Provider identities, read scopes, and credentials are configured by
          the server operator. Synchronize the catalog after configuration;
          names, TTLs, and read priority can be managed here.
        </Callout>
      )}
      <div className="two-columns">
        <div>
          <Panel
            title="Metadata read priority"
            action={<Status value="server persisted" />}
          >
            <p className="muted">
              Providers are read from top to bottom. Reordering changes metadata
              resolution, not where definitions are published.
            </p>
            {state.providers.map((p, i) => (
              <div className="provider-card" key={p.id}>
                <div className="provider-title">
                  <span className="order-number">{i + 1}</span>
                  <div>
                    <h3>{p.name}</h3>
                    <small>
                      {p.workspace} · {p.metastore}
                    </small>
                  </div>
                  <Status value={p.enabled ? p.health : "paused"} />
                </div>
                <div className="mini-row">
                  <span>Default TTL · {p.ttl} hours</span>
                  <span>{p.scope.join(", ")}</span>
                </div>
                <div className="inline">
                  <Button
                    aria-label={`Move ${p.name} up`}
                    disabled={i === 0}
                    icon={ArrowUp}
                    onClick={async () =>
                      await command("provider.reorder", { id: p.id, delta: -1 })
                    }
                  />
                  <Button
                    aria-label={`Move ${p.name} down`}
                    disabled={i === state.providers.length - 1}
                    icon={ArrowDown}
                    onClick={async () =>
                      await command("provider.reorder", { id: p.id, delta: 1 })
                    }
                  />
                  <Button
                    onClick={async () =>
                      await command("provider.update", {
                        id: p.id,
                        patch: { enabled: !p.enabled },
                      })
                    }
                  >
                    {p.enabled ? "Pause" : "Enable"}
                  </Button>
                  <Button onClick={() => setEdit(p.id)}>Configure</Button>
                </div>
              </div>
            ))}
          </Panel>
          <Callout>
            First sufficient evidence wins per fact. Missing and recoverable
            outages may fall through; authorization denials cannot use a
            replica.
          </Callout>
          <Panel title="Publication destinations">
            <p className="muted">
              Publication is a separate review and delivery step. Provider
              priority does not change these destination capabilities.
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Target</th>
                    <th>Delivery</th>
                    <th>Conditional update</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>UC descriptions / tags</td>
                    <td>{simulation ? "Simulated" : "Reviewed handoff"}</td>
                    <td>No atomic API assumed</td>
                  </tr>
                  <tr>
                    <td>Metric views</td>
                    <td>Validated YAML subset</td>
                    <td>No atomic API assumed</td>
                  </tr>
                  <tr>
                    <td>Genie Space</td>
                    <td>Full replacement</td>
                    <td>
                      {simulation ? "Mock ETag" : "Direct write unsupported"}
                    </td>
                  </tr>
                  <tr>
                    <td>Pages</td>
                    <td>Reviewed handoff</td>
                    <td>Unsupported direct write</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
        <div>
          <Panel title="Reader-scoped cache" action={<Clock size={20} />}>
            <p className="clock">
              {new Date(state.clock)
                .toISOString()
                .replace("T", " ")
                .slice(0, 16)}{" "}
              UTC
            </p>
            <div className="stats small-stats">
              <div>
                <strong>
                  {state.cache.filter((e) => e.expiresAt > state.clock).length}
                </strong>
                <span>Fresh facts</span>
              </div>
              <div>
                <strong>
                  {state.cache.filter((e) => e.expiresAt <= state.clock).length}
                </strong>
                <span>Expired facts</span>
              </div>
            </div>
            <div className="inline">
              <Button
                disabled={!simulation}
                onClick={async () =>
                  await command("clock.advance", { hours: 1 })
                }
              >
                Advance 1h
              </Button>
              <Button
                disabled={!simulation}
                onClick={async () =>
                  await command("clock.advance", { hours: 25 })
                }
              >
                Advance 25h
              </Button>
              <Button
                onClick={async () =>
                  await command(
                    "cache.clear",
                    {},
                    "Cache cleared; original retrieval observations retained.",
                  )
                }
              >
                Clear cache
              </Button>
            </div>
            <p className="muted">
              Reads do not reset retrieval time. Approval, policy and provider
              edits invalidate affected context.
            </p>
            {!state.cache.length && (
              <StateNotice title="No cached context yet">
                Resolve a question in Agent preview to inspect reader-scoped
                cached facts.
              </StateNotice>
            )}
            {state.cache.slice(0, 6).map((e) => (
              <div className="cache-row" key={e.key}>
                <span>
                  {e.fact.id} · {e.fact.evidence.providerId}
                  <small>
                    {e.reader} · retrieved{" "}
                    {new Date(e.retrievedAt).toISOString().slice(11, 16)}
                  </small>
                </span>
                <Status value={e.expiresAt > state.clock ? "fresh" : "stale"} />
              </div>
            ))}
          </Panel>
          <Panel title="TTL recommendation">
            {rec ? (
              <>
                <Status value="Pending acceptance" />
                <p>
                  {rec.count} actual fetches of <strong>{rec.factId}</strong>{" "}
                  for{" "}
                  {state.knowledge.find((k) => k.id === rec.knowledgeId)?.name}{" "}
                  occurred within one {simulation ? "mock " : ""}hour.
                </p>
                <p>
                  Suggest an object TTL of <strong>{rec.hours}h</strong>. This
                  can reduce repeat fetches, but may retain changed metadata
                  longer. Permission checks still apply.
                </p>
                {recEdit && (
                  <TextInput
                    label="Suggested TTL hours"
                    value={ttlEdit}
                    hint="Enter hours greater than 0 and up to 8760."
                    onChange={setTtlEdit}
                  />
                )}
                {recEdit &&
                  (!ttlEdit.trim() ||
                    !Number.isFinite(Number(ttlEdit)) ||
                    Number(ttlEdit) <= 0 ||
                    Number(ttlEdit) > 8760) && (
                    <p className="cg-error" role="alert">
                      Enter a TTL greater than 0 and no more than 8760 hours.
                    </p>
                  )}
                <div className="inline">
                  <Button
                    variant="primary"
                    disabled={
                      recEdit &&
                      (!ttlEdit.trim() ||
                        !Number.isFinite(Number(ttlEdit)) ||
                        Number(ttlEdit) <= 0 ||
                        Number(ttlEdit) > 8760)
                    }
                    onClick={async () =>
                      await command(
                        "ttl.accept",
                        {
                          knowledgeId: rec.knowledgeId,
                          hours: recEdit ? Number(ttlEdit) : rec.hours,
                        },
                        "TTL recommendation accepted.",
                      )
                    }
                  >
                    Apply TTL
                  </Button>
                  <Button
                    onClick={() => {
                      setRecEdit(true);
                      setTtlEdit(String(rec.hours));
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    onClick={async () => await command("ttl.dismiss", {})}
                  >
                    Dismiss
                  </Button>
                </div>
              </>
            ) : (
              <p className="muted">
                No pending recommendation. Resolve the same fact, clear cache,
                and repeat three times within one hour to observe a real
                retrieval pattern. No savings are claimed.
              </p>
            )}
          </Panel>
          {simulation &&
            state.knowledge.some((k) => k.id === "active-customer") &&
            state.knowledge.some((k) => k.id === "suspended-rule") &&
            state.providers.some((p) => p.id === "openmetadata") && (
              <Panel title="Precedence in practice">
                <p>
                  Lifecycle + OpenMetadata:{" "}
                  <strong>
                    {
                      ttl(
                        state,
                        state.knowledge.find(
                          (k) => k.id === "active-customer",
                        )!,
                        state.providers.find((p) => p.id === "openmetadata")!,
                      ).hours
                    }
                    h
                  </strong>
                </p>
                <p>
                  Retention + OpenMetadata:{" "}
                  <strong>
                    {
                      ttl(
                        state,
                        state.knowledge.find((k) => k.id === "suspended-rule")!,
                        state.providers.find((p) => p.id === "openmetadata")!,
                      ).hours
                    }
                    h
                  </strong>
                </p>
                <p className="muted">
                  Retention's explicit domain override masks the provider
                  default. Enterprise's 24h is only the workspace fallback.
                </p>
              </Panel>
            )}
        </div>
      </div>
      {p && <ProviderForm provider={p} onClose={() => setEdit(null)} />}{" "}
      {adding && <ProviderForm onClose={() => setAdding(false)} />}
    </div>
  );
}
function ProviderForm({
  provider,
  onClose,
}: {
  provider?: Provider;
  onClose: () => void;
}) {
  const { command, simulation } = useRepo();
  const [name, setName] = useState(
      provider?.name || "Unity Catalog — New instance",
    ),
    [kind, setKind] = useState(provider?.kind || "uc"),
    [hours, setHours] = useState(String(provider?.ttl || 24)),
    [health, setHealth] = useState(provider?.health || "healthy"),
    [scope, setScope] = useState(provider?.scope.join(", ") || "customer"),
    [workspace, setWorkspace] = useState(
      provider?.workspace || "demo-workspace",
    ),
    [metastore, setMetastore] = useState(
      provider?.metastore || "demo-metastore",
    );
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const errors = [
    !name.trim() && "Enter an instance name.",
    !workspace.trim() && "Enter a workspace.",
    !metastore.trim() && "Enter a metastore.",
    (!hours.trim() ||
      !Number.isFinite(Number(hours)) ||
      Number(hours) <= 0 ||
      Number(hours) > 8760) &&
      "TTL must be greater than 0 and no more than 8760 hours.",
    (!scope.trim() || scope.split(",").some((x) => !x.trim())) &&
      "Enter domain IDs separated by commas, without empty entries.",
  ].filter(Boolean);
  const dirty =
    name !== (provider?.name || "Unity Catalog — New instance") ||
    kind !== (provider?.kind || "uc") ||
    hours !== String(provider?.ttl || 24) ||
    health !== (provider?.health || "healthy") ||
    scope !== (provider?.scope.join(", ") || "customer") ||
    workspace !== (provider?.workspace || "demo-workspace") ||
    metastore !== (provider?.metastore || "demo-metastore");
  const guard = useDraftGuard(dirty, "provider configuration");
  const close = () => {
    if (!saving) guard.attempt(onClose);
  };
  return (
    <Modal
      title={provider ? "Configure provider instance" : "Add provider instance"}
      onClose={close}
    >
      <p className="cg-draft-status" role="status">
        {dirty
          ? "Unsaved configuration changes"
          : provider
            ? "Configuration saved"
            : "New provider · not added yet"}
      </p>
      {attempted && errors.length > 0 && (
        <div className="cg-error" role="alert">
          <strong>Check the provider details</strong>
          <ul>
            {errors.map((error) => (
              <li key={String(error)}>{error}</li>
            ))}
          </ul>
        </div>
      )}
      <fieldset
        disabled={saving}
        style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
      >
        <TextInput label="Instance name" value={name} onChange={setName} />
        {simulation ? (
          <Select
            label="Provider kind"
            value={kind}
            onChange={(v) => setKind(v as any)}
            options={opts(["uc", "openmetadata", "authored"])}
          />
        ) : (
          <KeyValue
            items={{
              Kind: kind,
              Workspace: workspace,
              Metastore: metastore,
              "Read scope": scope,
            }}
          />
        )}
        <div className="form-grid">
          {simulation && (
            <>
              <TextInput
                label="Workspace"
                value={workspace}
                onChange={setWorkspace}
              />
              <TextInput
                label="Metastore"
                value={metastore}
                onChange={setMetastore}
              />
            </>
          )}
          <TextInput
            label="Default TTL hours"
            value={hours}
            hint="Greater than 0, up to 8760 hours."
            onChange={setHours}
          />
          {simulation && (
            <Select
              label="Simulated health"
              value={health}
              onChange={(v) => setHealth(v as any)}
              options={opts(["healthy", "outage", "denied", "malformed"])}
            />
          )}
        </div>
        {simulation && (
          <TextInput
            label="Metadata scope (domain IDs, comma separated)"
            value={scope}
            onChange={setScope}
          />
        )}
        <Callout>
          {simulation
            ? "No credentials. Added instances have no seeded fact evidence until explicitly supplied in fixtures."
            : "Provider name and TTL are saved on the server. Provider identity, read scope, and credentials are controlled by the server operator."}
        </Callout>
        <div className="cg-form-actions">
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            disabled={saving || (!!provider && !dirty)}
            onClick={async () => {
              setAttempted(true);
              if (errors.length || saving || (provider && !dirty)) return;
              setSaving(true);
              const patch = {
                name: name.trim(),
                kind,
                ttl: Number(hours),
                health,
                scope: scope.split(",").map((x) => x.trim()),
                workspace: workspace.trim(),
                metastore: metastore.trim(),
              };
              const ok = provider
                ? await command(
                    "provider.update",
                    {
                      id: provider.id,
                      patch: simulation
                        ? patch
                        : { name: patch.name, ttl: patch.ttl },
                    },
                    "Provider configuration saved; cache invalidated.",
                  )
                : await command(
                    "provider.create",
                    {
                      provider: {
                        ...patch,
                        enabled: true,
                        capabilities: {
                          discovery: "permitted",
                          inspection: "permitted",
                          data: "denied",
                          modification: "unsupported",
                          management: "unknown",
                        },
                      },
                    },
                    "Provider configuration saved; cache invalidated.",
                  );
              setSaving(false);
              if (ok) {
                guard.markClean();
                onClose();
              }
            }}
          >
            {saving
              ? "Saving…"
              : provider
                ? "Save configuration"
                : "Add provider"}
          </Button>
        </div>
      </fieldset>
    </Modal>
  );
}
