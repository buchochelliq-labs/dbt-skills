import React, { useState } from "react";
import {
  Button,
  Panel,
  Title,
  TextInput,
  Select,
  Json,
  StateNotice,
  downloadJSON,
  Status,
} from "./components";
import {
  localRequest,
  callCore,
  type LocalContext,
  type WorkspaceSnapshot,
  type AuthoredRecord,
} from "./localService";
import { useDraftGuard } from "./draftGuard";
export function ConnectedWorkspace({ onDemo }: { onDemo: () => void }) {
  const [context, setContext] = useState<LocalContext | null>(null),
    [providers, setProviders] = useState<any[]>([]),
    [provider, setProvider] = useState(""),
    [assets, setAssets] = useState<any[]>([]),
    [selected, setSelected] = useState<string[]>([]),
    [query, setQuery] = useState(""),
    [intent, setIntent] = useState(
      "Design a data model across the selected entities. Explain relationships, grain and evidence gaps.",
    ),
    [directory, setDirectory] = useState("models/staging"),
    [plan, setPlan] = useState<any>(null),
    [rules, setRules] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null),
    [tab, setTab] = useState("Context"),
    [importText, setImportText] = useState(""),
    [preview, setPreview] = useState<any>(null),
    [publication, setPublication] = useState(""),
    [preflight, setPreflight] = useState<any>(null);
  const empty = (): AuthoredRecord => ({
    id: "",
    kind: "knowledge",
    title: "",
    content: "",
    references: [],
    evidence: [],
    approval: "draft",
  });
  const [draft, setDraft] = useState<AuthoredRecord>(empty),
    [baseline, setBaseline] = useState(JSON.stringify(empty()));
  const guard = useDraftGuard(
    JSON.stringify(draft) !== baseline || !!importText || !!publication,
    "Local authored workspace",
    () => {
      setDraft(empty());
      setBaseline(JSON.stringify(empty()));
      setImportText("");
      setPublication("");
      setPreview(null);
    },
  );
  async function run(action: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function connect() {
    await run(async () => {
      const c = await localRequest<LocalContext>("context");
      const s = await callCore("catalog_status", { context_id: c.context_id });
      const w = await localRequest<WorkspaceSnapshot>("workspace/read");
      setContext(c);
      setProviders(s.providers);
      setProvider(s.providers[0]?.id || "");
      setWorkspace(w);
      setAssets([]);
      setSelected([]);
      setPlan(null);
    });
  }
  const args = () => ({ context_id: context!.context_id });
  return (
    <div className="connected-workspace">
      <header className="connected-header">
        <strong>UOL · Local project</strong>
        <Status value="Backend context" />
        <Button onClick={() => guard.attempt(onDemo)}>
          Open simulated demo
        </Button>
      </header>
      <main className="connected-main">
        <Title
          eyebrow="Provider-neutral · metadata only"
          title="From project evidence to a data model"
          description="Use the same context service as an agent. Source records and native writes are not available."
        />
        <div className="inline">
          <Button variant="primary" disabled={busy} onClick={connect}>
            {context ? "Reconnect selected project" : "Connect local backend"}
          </Button>
          {context && (
            <>
              <span>
                {context.project_name} · {context.context_id.slice(0, 8)}
              </span>
              <Button
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const c = await callCore("catalog_sync", args());
                    setContext(c);
                    setPlan(null);
                    setSelected([]);
                    setAssets([]);
                  })
                }
              >
                Sync project delta
              </Button>
            </>
          )}
        </div>
        {error && (
          <StateNotice kind="error" title="Local request did not complete">
            {error}
          </StateNotice>
        )}
        {busy && <p role="status">Working with the local service…</p>}
        {!context && (
          <Panel title="Connect once, keep context local">
            <p>
              Start the Python application service and the same-origin frontend
              proxy as described in the local integration guide. Authentication
              stays in the local proxy; provider credentials never enter this
              page.
            </p>
            <p>The disconnected state does not substitute fictional facts.</p>
          </Panel>
        )}
        {context && (
          <>
            <nav
              className="connected-tabs"
              aria-label="Local workspace sections"
            >
              {["Context", "Authored workspace", "Native handoff"].map((t) => (
                <Button
                  key={t}
                  onClick={() => setTab(t)}
                  aria-pressed={tab === t}
                >
                  {t}
                </Button>
              ))}
            </nav>
            {tab === "Context" && (
              <div className="connected-grid">
                <section>
                  <Panel title="1. Select project metadata">
                    <Select
                      label="Metadata provider"
                      value={provider}
                      onChange={setProvider}
                      options={providers.map((p) => ({
                        value: p.id,
                        label: `${p.id} · ${p.type} · ${p.status}`,
                      }))}
                    />
                    <TextInput
                      label="Search asset identifiers"
                      value={query}
                      onChange={setQuery}
                    />
                    <Button
                      disabled={busy || !provider}
                      onClick={() =>
                        run(async () => {
                          const r = await callCore("catalog_search", {
                            ...args(),
                            provider_id: provider,
                            query,
                          });
                          setAssets(r.assets || []);
                          if (r.status !== "available")
                            setError(`Provider result: ${r.status}`);
                        })
                      }
                    >
                      Search selected provider
                    </Button>
                    {assets.map((a) => (
                      <label className="check" key={a.asset_id}>
                        <input
                          type="checkbox"
                          checked={selected.includes(a.asset_id)}
                          onChange={(e) =>
                            setSelected(
                              e.target.checked
                                ? [...selected, a.asset_id]
                                : selected.filter((i) => i !== a.asset_id),
                            )
                          }
                        />
                        {a.asset_id}
                      </label>
                    ))}
                    <p>
                      {selected.length} selected · maximum 8. Only selected
                      project assets are resolved.
                    </p>
                  </Panel>
                  <Panel title="2. State the design goal">
                    <TextInput
                      label="Data-model goal"
                      value={intent}
                      onChange={setIntent}
                      area
                    />
                    <TextInput
                      label="Modelling directory scope"
                      value={directory}
                      onChange={setDirectory}
                    />
                    <div className="inline">
                      <Button
                        disabled={busy}
                        onClick={() =>
                          run(async () =>
                            setRules(
                              await callCore("modelling_rules", {
                                ...args(),
                                section: "modelling",
                              }),
                            ),
                          )
                        }
                      >
                        Read modelling standards
                      </Button>
                      <Button
                        variant="primary"
                        disabled={
                          busy ||
                          !selected.length ||
                          selected.length > 8 ||
                          !intent.trim()
                        }
                        onClick={() =>
                          run(async () =>
                            setPlan(
                              await callCore("model_plan", {
                                ...args(),
                                request: {
                                  intent,
                                  assets: selected.map((asset_id) => ({
                                    asset_id,
                                    scope: directory ? { directory } : {},
                                  })),
                                },
                              }),
                            ),
                          )
                        }
                      >
                        Assemble design context
                      </Button>
                    </div>
                    {rules && <Json value={rules} />}
                  </Panel>
                </section>
                <section>
                  <Panel title="3. Review evidence and questions">
                    {!plan ? (
                      <p>
                        Choose assets and assemble context. The agent supplies
                        design reasoning; the backend supplies grounding.
                      </p>
                    ) : (
                      <>
                        <Status value={plan.status} />
                        <p>
                          {plan.entities?.length || 0} entity candidates ·{" "}
                          {plan.relationships?.length || 0} declared
                          relationships
                        </p>
                        {plan.questions?.map((q: any, i: number) => (
                          <p key={i}>
                            <strong>{q.code}</strong> — {q.message}
                          </p>
                        ))}
                        <details>
                          <summary>Entity and relationship evidence</summary>
                          <Json
                            value={{
                              entities: plan.entities,
                              relationships: plan.relationships,
                              evidence: plan.evidence,
                              policy_provenance: plan.policy_provenance,
                              limitations: plan.limitations,
                            }}
                          />
                        </details>
                        <div className="inline">
                          <Button
                            onClick={() =>
                              downloadJSON(
                                {
                                  schema_version: 1,
                                  simulation: false,
                                  context: plan,
                                },
                                "uol-project-context.json",
                              )
                            }
                          >
                            Export grounded context
                          </Button>
                          <Button
                            onClick={() => {
                              const d: AuthoredRecord = {
                                id: `design-${Date.now()}`,
                                kind: "design",
                                title: "Data model review",
                                content: plan.intent,
                                references: selected,
                                evidence: [
                                  {
                                    origin: "project-manifest",
                                    revision: String(
                                      context.source.sha256 || "unknown",
                                    ),
                                  },
                                  {
                                    origin: "modelling-policy",
                                    revision:
                                      plan.policy_provenance?.sha256 ||
                                      "unknown",
                                  },
                                ],
                                approval: "draft",
                              };
                              setDraft(d);
                              setBaseline(JSON.stringify(empty()));
                              setTab("Authored workspace");
                            }}
                          >
                            Write a design decision
                          </Button>
                        </div>
                      </>
                    )}
                  </Panel>
                  <Panel title="Provider status & provenance">
                    <p>
                      Priority is supplied by backend configuration, not this
                      browser. Change configuration locally, then reconnect.
                    </p>
                    <details>
                      <summary>Configured metadata providers</summary>
                      <Json value={providers} />
                    </details>
                  </Panel>
                </section>
              </div>
            )}
            {tab === "Authored workspace" && workspace && (
              <div className="connected-grid">
                <section>
                  <Panel
                    title={`Durable records · revision ${workspace.revision}`}
                  >
                    <p>
                      Encrypted locally. Authored knowledge and review history
                      do not expire with provider cache TTL.
                    </p>
                    <Button
                      onClick={() =>
                        run(async () =>
                          setWorkspace(await localRequest("workspace/read")),
                        )
                      }
                    >
                      Reload saved records
                    </Button>
                    {workspace.document.records.map((r) => (
                      <button
                        className="object-row"
                        key={r.id}
                        onClick={() =>
                          guard.attempt(() => {
                            setDraft(structuredClone(r));
                            setBaseline(JSON.stringify(r));
                          })
                        }
                      >
                        <strong>{r.title}</strong>
                        <span>
                          {r.kind} · {r.approval || "draft"}
                        </span>
                      </button>
                    ))}
                    <Button
                      onClick={() =>
                        guard.attempt(() => {
                          setDraft(empty());
                          setBaseline(JSON.stringify(empty()));
                        })
                      }
                    >
                      New authored record
                    </Button>
                    <details>
                      <summary>Review history</summary>
                      <Json value={workspace.history || []} />
                    </details>
                  </Panel>
                  <Panel title="Validated import / export">
                    <Button
                      onClick={() =>
                        run(async () =>
                          downloadJSON(
                            await localRequest("workspace/export"),
                            "uol-authored-workspace.json",
                          ),
                        )
                      }
                    >
                      Export authored workspace
                    </Button>
                    <TextInput
                      label="Workspace import JSON"
                      value={importText}
                      onChange={(v) => {
                        setImportText(v);
                        setPreview(null);
                      }}
                      area
                    />
                    <Button
                      disabled={busy || !importText}
                      onClick={() =>
                        run(async () =>
                          setPreview(
                            await localRequest(
                              "workspace/import/preview",
                              JSON.parse(importText),
                            ),
                          ),
                        )
                      }
                    >
                      Validate and preview import
                    </Button>
                    {preview && (
                      <>
                        <Json value={preview} />
                        <p>
                          Replacement removes listed records. Imported approvals
                          reset to draft.
                        </p>
                        <Button
                          onClick={() =>
                            run(async () => {
                              setWorkspace(
                                await localRequest("workspace/import/apply", {
                                  preview_id: preview.preview_id,
                                }),
                              );
                              setImportText("");
                              setPreview(null);
                            })
                          }
                        >
                          Apply reviewed import
                        </Button>
                      </>
                    )}
                  </Panel>
                </section>
                <Panel title="Authored metadata record">
                  <TextInput
                    label="Stable record ID"
                    value={draft.id}
                    onChange={(id) => setDraft({ ...draft, id })}
                  />
                  <Select
                    label="Record type"
                    value={draft.kind}
                    onChange={(kind) =>
                      setDraft({ ...draft, kind: kind as any })
                    }
                    options={[
                      "domain",
                      "knowledge",
                      "mapping",
                      "configuration",
                      "review",
                      "design",
                    ].map((value) => ({ value, label: value }))}
                  />
                  <TextInput
                    label="Record title"
                    value={draft.title}
                    onChange={(title) => setDraft({ ...draft, title })}
                  />
                  <TextInput
                    label="Definition / decision and rationale"
                    value={draft.content}
                    onChange={(content) => setDraft({ ...draft, content })}
                    area
                  />
                  <TextInput
                    label="References (one identity per line)"
                    value={draft.references.join("\n")}
                    onChange={(v) =>
                      setDraft({
                        ...draft,
                        references: v
                          .split("\n")
                          .map((s) => s.trim())
                          .filter(Boolean),
                      })
                    }
                    area
                  />
                  <Select
                    label="Local review state"
                    value={draft.approval || "draft"}
                    onChange={(v) => setDraft({ ...draft, approval: v as any })}
                    options={[
                      { value: "draft", label: "Draft" },
                      { value: "reviewed", label: "Reviewed locally" },
                    ]}
                  />
                  <p>
                    Local review does not grant provider permission or approve
                    publication.
                  </p>
                  <Button
                    variant="primary"
                    disabled={busy || !draft.id.trim() || !draft.title.trim()}
                    onClick={() =>
                      run(async () => {
                        const records = workspace.document.records.filter(
                          (r) => r.id !== draft.id,
                        );
                        const next = await localRequest<WorkspaceSnapshot>(
                          "workspace/save",
                          {
                            expected_revision: workspace.revision,
                            document: {
                              schema_version: 1,
                              records: [...records, draft],
                            },
                            reason: `Saved ${draft.kind} record`,
                          },
                        );
                        setWorkspace(next);
                        setBaseline(JSON.stringify(draft));
                        guard.markClean();
                      })
                    }
                  >
                    Save durable record
                  </Button>
                  <details>
                    <summary>Retained evidence</summary>
                    <Json value={draft.evidence} />
                  </details>
                </Panel>
              </div>
            )}
            {tab === "Native handoff" && (
              <Panel title="Separate native publication preflight">
                <p>
                  No authenticated publication adapter is enabled. Checks return
                  unsupported until configured and validated; the reviewed
                  export is usable for a manual handoff. No live writes are
                  exposed.
                </p>
                <TextInput
                  label="Native proposal JSON"
                  value={publication}
                  onChange={(v) => {
                    setPublication(v);
                    setPreflight(null);
                  }}
                  area
                />
                <Button
                  disabled={busy || !publication}
                  onClick={() =>
                    run(async () =>
                      setPreflight(
                        await localRequest(
                          "publication/check",
                          JSON.parse(publication),
                        ),
                      ),
                    )
                  }
                >
                  Check publication proposal
                </Button>
                {preflight && (
                  <>
                    <Json value={preflight} />
                    <Button
                      onClick={() =>
                        run(async () =>
                          downloadJSON(
                            await localRequest(
                              "publication/export",
                              JSON.parse(publication),
                            ),
                            "uol-native-review-handoff.json",
                          ),
                        )
                      }
                    >
                      Export selected changes for review
                    </Button>
                  </>
                )}
              </Panel>
            )}
          </>
        )}
      </main>
    </div>
  );
}
