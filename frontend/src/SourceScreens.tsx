import { useNavigationGuard, useDraftGuard } from "./draftGuard";
import React, { useState, useEffect } from "react";
import {
  Database,
  ArrowRight,
  Link,
  Download,
  TreeStructure,
} from "@phosphor-icons/react";
import { useRepo } from "./store";
import {
  assetView,
  knowledgeView,
  mayInspect,
  exportEnvelope,
  projection,
  HOUR,
} from "./services";
import type { SourceAsset, SourceField } from "./contracts";
import { MappingReviewActions } from "./MappingReviewActions";
import {
  Panel,
  Title,
  Button,
  Status,
  TextInput,
  Select,
  opts,
  KeyValue,
  Callout,
  Json,
  Modal,
  StateNotice,
  Tabs,
  TypeIcon,
  downloadJSON,
  PermissionSummary,
} from "./components";
import { GraphScreen } from "./GraphScreen";
import { Changes, ProposalDialog } from "./ChangesScreen";
import { MetricEditor, PagesEditor, GenieEditor } from "./SemanticEditors";
export function Sources({
  onObject,
  onContext,
  requestedAsset,
}: {
  requestedAsset?: { id: string; sequence: number };
  onObject: (id: string) => void;
  onContext: (id?: string) => void;
}) {
  const { state, reader, simulation } = useRepo();
  const attempt = useNavigationGuard();
  const [section, rawSection] = useState("Catalog explorer"),
    [selected, setSelected] = useState(""),
    [selectedProvider, setProvider] = useState(""),
    [q, setQ] = useState(""),
    [type, setType] = useState("All");
  const setSection = (v: string) => attempt(() => rawSection(v));
  const provider = state.providers.some((p) => p.id === selectedProvider)
    ? selectedProvider
    : (state.providers.find((p) => p.kind === "uc") || state.providers[0])
        ?.id || "";
  const assets = assetView(state, reader).filter(
    (a) => a.providerId === provider,
  );
  const a = assets.find((a) => a.id === selected);
  const p = state.providers.find((p) => p.id === provider)!;
  const matches = assets.filter(
    (a) =>
      (type === "All" || a.type === type) &&
      a.name.toLowerCase().includes(q.toLowerCase()),
  );
  const browse = !a || !!q || type !== "All";
  function openAsset(id: string) {
    setSelected(id);
    setQ("");
    setType("All");
    setSection("Catalog explorer");
    window.scrollTo(0, 0);
  }
  function browseAssets() {
    setSelected("");
    setQ("");
    setType("All");
    setSection("Catalog explorer");
    window.scrollTo(0, 0);
  }
  useEffect(() => {
    if (!requestedAsset) return;
    const target = assetView(state, reader).find(
      (a) => a.id === requestedAsset.id,
    );
    if (target) {
      setProvider(target.providerId);
      openAsset(target.id);
    }
  }, [requestedAsset]);
  const sections = [
    "Catalog explorer",
    "Discover & projection",
    "Pages",
    "Genie context",
    "Mappings",
    "Access & capabilities",
    "Native review",
  ];
  if (!p)
    return (
      <StateNotice title="No source providers configured">
        Configure a project source provider, then sync the catalog to browse its
        metadata.
      </StateNotice>
    );
  return (
    <div className="source-shell">
      <div className="source-banner">
        <span>
          <Database size={18} />
          {p.kind === "uc"
            ? "UOL / Unity Catalog companion"
            : "Sources / Project metadata"}
        </span>
        <small>
          {simulation ? "Simulated integration" : "Local backend"} · UOL-owned
          screens
        </small>
      </div>
      <div className="source-layout">
        <aside className="catalog-nav">
          <div className="eyebrow">SOURCE INSTANCE</div>
          <Select
            label="Catalog connection"
            value={provider}
            onChange={(v) =>
              attempt(() => {
                setProvider(v);
                setSelected("");
              })
            }
            options={state.providers.map((p) => ({
              value: p.id,
              label: p.name.replace(/^Unity Catalog — /, ""),
            }))}
          />
          <details className="connection-details">
            <summary>Workspace & metastore</summary>
            <p>{p.workspace}</p>
            <p>{p.metastore}</p>
          </details>
          <div className="mobile-source-section">
            <Select
              label="Source workspace"
              value={section}
              onChange={(v) => {
                setSection(v);
                window.scrollTo(0, 0);
              }}
              options={opts(sections)}
            />
          </div>
          <nav className="source-sections" aria-label="UC companion navigation">
            <button
              aria-current={section === "Catalog explorer" ? "page" : undefined}
              className={section === "Catalog explorer" ? "selected" : ""}
              onClick={browseAssets}
            >
              <Database size={17} /> Browse assets <span>{assets.length}</span>
            </button>
            <button
              aria-current={section === "Mappings" ? "page" : undefined}
              className={section === "Mappings" ? "selected" : ""}
              onClick={() => setSection("Mappings")}
            >
              <Link size={17} /> Semantic mappings
            </button>
          </nav>
          {section === "Catalog explorer" && (
            <div className="catalog-tree-section">
              <div className="eyebrow">CATALOGS & SCHEMAS</div>
              <CatalogTree
                assets={assets}
                selected={selected}
                onSelect={openAsset}
              />
            </div>
          )}
          <details
            className="source-tools"
            open={
              !["Catalog explorer", "Mappings"].includes(section) || undefined
            }
          >
            <summary>Pages, Genie & governance</summary>
            <nav aria-label="Native semantic tools">
              {sections
                .filter((v) => !["Catalog explorer", "Mappings"].includes(v))
                .map((v) => (
                  <button
                    key={v}
                    className={section === v ? "selected" : ""}
                    onClick={() => {
                      setSection(v);
                      window.scrollTo(0, 0);
                    }}
                  >
                    {v}
                  </button>
                ))}
            </nav>
          </details>
        </aside>
        <div className="source-main">
          {section === "Catalog explorer" && (
            <>
              {!browse && (
                <button className="back-link" onClick={browseAssets}>
                  ← Back to source assets
                </button>
              )}
              <Title
                eyebrow={
                  browse ? "Project metadata" : a!.type.replace("_", " ")
                }
                title={
                  browse ? "Browse source assets" : a!.name.split(".").at(-1)!
                }
                description={
                  browse
                    ? "Find the tables, views and metrics that ground your business knowledge."
                    : a!.name
                }
              />
              {browse && (
                <div className="toolbar catalog-search">
                  <input
                    aria-label="Search catalog"
                    placeholder="Search catalogs, tables, metric views…"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                  />
                  <select
                    aria-label="Object type"
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                  >
                    {[
                      "All",
                      "catalog",
                      "schema",
                      "table",
                      "view",
                      "metric_view",
                    ].map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                  <span className="result-count" role="status">
                    {matches.length} assets
                  </span>
                </div>
              )}
              {browse ? (
                <>
                  <div className="object-list">
                    {matches.map((a) => (
                      <button
                        className="object-row"
                        key={a.id}
                        onClick={() => openAsset(a.id)}
                      >
                        <TypeIcon type={a.type} />
                        <span>
                          <strong>{a.name}</strong>
                          <small>
                            {a.type} · {a.owner}
                          </small>
                        </span>
                        <Status
                          value={
                            state.clock - a.observedAt > 24 * HOUR
                              ? "stale"
                              : p.health
                          }
                        />
                        <ArrowRight size={16} />
                      </button>
                    ))}
                  </div>
                  {!matches.length && (
                    <StateNotice
                      title={
                        assets.length
                          ? "No matching assets"
                          : "No permitted assets in this instance"
                      }
                    >
                      {assets.length
                        ? "Try a different name or clear the filters."
                        : "Sync this provider to load permitted source metadata."}
                      <Button
                        onClick={() => {
                          setQ("");
                          setType("All");
                        }}
                      >
                        Clear filters
                      </Button>
                    </StateNotice>
                  )}
                </>
              ) : (
                <AssetDetail
                  key={a!.id}
                  asset={a!}
                  onSelect={setSelected}
                  onObject={onObject}
                  onContext={onContext}
                />
              )}
            </>
          )}
          {section === "Mappings" && (
            <>
              <Title
                eyebrow="Connect meaning"
                title="Semantic mapping workbench"
                description="Map business meaning to permitted technical metadata. Field identity is separate from its containing asset."
              />
              <MappingWorkbench onObject={onObject} />
            </>
          )}
          {section === "Discover & projection" && <ProjectionEditor />}
          {section === "Pages" && <PagesEditor />}
          {section === "Genie context" && <GenieEditor />}
          {section === "Access & capabilities" && (
            <>
              <Title
                eyebrow="Governance"
                title="Access & capabilities"
                description="Read-only permission simulation. UOL ownership and native access are separate."
              />
              <Access providerId={provider} />
            </>
          )}
          {section === "Native review" && <Changes />}
        </div>
      </div>
    </div>
  );
}
function CatalogTree({
  assets,
  selected,
  onSelect,
}: {
  assets: SourceAsset[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [closed, setClosed] = useState<string[]>([]);
  function branch(a: SourceAsset, depth: number): React.ReactNode {
    const children = assets.filter((x) => x.parent === a.id),
      open = !closed.includes(a.id);
    return (
      <div key={a.id}>
        <div
          className={`catalog-tree-row ${a.id === selected ? "selected" : ""}`}
          style={{ paddingLeft: depth * 12 }}
        >
          {children.length > 0 && (
            <button
              aria-label={`${open ? "Collapse" : "Expand"} ${a.name}`}
              onClick={() =>
                setClosed(
                  open ? [...closed, a.id] : closed.filter((id) => id !== a.id),
                )
              }
            >
              {open ? "−" : "+"}
            </button>
          )}
          <button onClick={() => onSelect(a.id)}>
            <TypeIcon type={a.type} />
            <span>{a.name.split(".").at(-1)}</span>
          </button>
        </div>
        {open && children.map((c) => branch(c, depth + 1))}
      </div>
    );
  }
  return (
    <nav aria-label="Catalog hierarchy">
      {assets
        .filter((a) => !a.parent || !assets.some((x) => x.id === a.parent))
        .map((a) => branch(a, 0))}
    </nav>
  );
}
function AssetDetail({
  asset: a,
  onSelect,
  onObject,
  onContext,
}: {
  asset: SourceAsset;
  onSelect: (id: string) => void;
  onObject: (id: string) => void;
  onContext: (id?: string) => void;
}) {
  const { state, reader } = useRepo();
  const attempt = useNavigationGuard();
  const [tab, setTab] = useState("Overview"),
    [column, setColumn] = useState<SourceField | null>(null),
    [proposal, setProposal] = useState<string | null>(null),
    [evidenceOpen, setEvidenceOpen] = useState(false),
    [mappingStart, setMappingStart] = useState(0);
  const target = state.targets.find((t) => t.id === a.id);
  const container = ["catalog", "schema"].includes(a.type);
  const linkedKnowledgeIds = [
    ...new Set([
      ...a.knowledgeIds,
      ...state.mappings
        .filter((m) => m.assetId === a.id)
        .map((m) => m.knowledgeId),
    ]),
  ].filter((id) => knowledgeView(state, reader).some((k) => k.id === id));
  return (
    <>
      <div className="inline">
        <Status value="Imported source metadata" />
        <Status
          value={state.clock - a.observedAt > 24 * HOUR ? "stale" : "fresh"}
        />
        <span>{a.type.replace("_", " ")}</span>
      </div>
      <div className="crumbs">
        {a.name.split(".").map((part, i) => (
          <button
            key={i}
            onClick={() => {
              const found = state.assets.find(
                (x) =>
                  x.providerId === a.providerId &&
                  x.name ===
                    a.name
                      .split(".")
                      .slice(0, i + 1)
                      .join("."),
              );
              if (found) onSelect(found.id);
            }}
          >
            {part}
            <span>/</span>
          </button>
        ))}
      </div>
      <div className="asset-actions">
        {!container && (
          <Button
            variant="primary"
            icon={Link}
            onClick={() => {
              setMappingStart((n) => n + 1);
              setTab("Semantic mappings");
            }}
          >
            Link business meaning
          </Button>
        )}
        <Button disabled={!target} onClick={() => setProposal("description")}>
          Suggest an edit
        </Button>
        <Button
          aria-haspopup="dialog"
          onClick={() => setEvidenceOpen(!evidenceOpen)}
        >
          Source evidence
        </Button>
      </div>
      {evidenceOpen && (
        <Modal
          title="Source evidence"
          description={a.name}
          drawer
          onClose={() => setEvidenceOpen(false)}
        >
          <div>
            <h3>Identity & provenance</h3>
            <KeyValue
              items={{
                "Provider instance": a.providerId,
                "Native ID": a.nativeId,
                "Source revision": a.sourceRevision,
                "Observed at": new Date(a.observedAt).toISOString(),
              }}
            />
          </div>
          {target ? (
            <details>
              <summary>
                Inspect target metadata · revision {target.revision}
              </summary>
              <Json value={target.content} />
              <p className="muted">
                The imported observation stays separate until a provider sync.
                This is the session target store.
              </p>
            </details>
          ) : (
            <StateNotice title="No editable target metadata supplied" />
          )}
        </Modal>
      )}
      <Tabs
        items={
          container
            ? ["Overview", "Changes"]
            : [
                "Overview",
                "Columns",
                "Semantic mappings",
                "Lineage",
                "Access",
                "Changes",
                ...(a.type === "metric_view" ? ["Metric editor"] : []),
              ]
        }
        value={tab}
        onChange={(v) => attempt(() => setTab(v))}
      />
      {tab === "Overview" && (
        <>
          <Panel title="About this asset">
            <p className="definition-lead small-lead">{a.description}</p>
            <div className="asset-summary-grid">
              <div>
                <span>Accountable team</span>
                <strong>{a.owner}</strong>
              </div>
              <div>
                <span>Business domains</span>
                <strong>
                  {a.domainIds
                    .map((id) => state.domains.find((d) => d.id === id)?.name)
                    .join(", ") || "Not linked"}
                </strong>
              </div>
              {!container && (
                <div>
                  <span>Schema</span>
                  <strong>
                    {a.fields.length
                      ? `${a.fields.length} declared fields`
                      : "Not supplied"}
                  </strong>
                </div>
              )}
            </div>
            <div className="asset-tags">
              <span>Governed tags</span>
              {Object.entries(a.tags).map(([k, v]) => (
                <span className="tag" key={k}>
                  {k}
                  {v ? ` · ${v}` : ""}
                </span>
              ))}
              <button className="text-link" onClick={() => setProposal("tags")}>
                Propose tags
              </button>
            </div>
          </Panel>
          <Panel
            title={container ? "Explore child assets" : "Business meaning"}
          >
            {container
              ? assetView(state, reader)
                  .filter((x) => x.parent === a.id)
                  .map((x) => (
                    <button
                      className="object-row"
                      key={x.id}
                      onClick={() => onSelect(x.id)}
                    >
                      <TypeIcon type={x.type} />
                      <span>{x.name}</span>
                      <ArrowRight />
                    </button>
                  ))
              : linkedKnowledgeIds
                  .filter((id) =>
                    knowledgeView(state, reader).some((k) => k.id === id),
                  )
                  .map((id) => (
                    <button
                      className="object-row"
                      key={id}
                      onClick={() => onObject(id)}
                    >
                      <TypeIcon
                        type={state.knowledge.find((k) => k.id === id)!.type}
                      />
                      <span>
                        <strong>
                          {state.knowledge.find((k) => k.id === id)!.name}
                        </strong>
                        <small>
                          {state.knowledge.find((k) => k.id === id)!.definition}
                        </small>
                      </span>
                      <Status
                        value={
                          [
                            ...new Set(
                              state.mappings
                                .filter(
                                  (m) =>
                                    m.assetId === a.id && m.knowledgeId === id,
                                )
                                .map((m) => m.status),
                            ),
                          ].join(" / ") || "Imported link"
                        }
                      />
                      <ArrowRight />
                    </button>
                  ))}
            {!container && !linkedKnowledgeIds.length && (
              <StateNotice title="No semantic mappings supplied">
                Create a draft in Semantic mappings.
              </StateNotice>
            )}
          </Panel>
        </>
      )}
      {tab === "Columns" && (
        <Panel title="Column definitions">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Type</th>
                  <th>Nullable</th>
                  <th>Key declaration</th>
                  <th>Mappings</th>
                </tr>
              </thead>
              <tbody>
                {a.fields.map((f) => (
                  <tr key={f.path}>
                    <td>
                      <button
                        className="text-link"
                        onClick={() => setColumn(f)}
                      >
                        {f.path}
                      </button>
                    </td>
                    <td>{f.type}</td>
                    <td>{f.nullable ? "Yes" : "No"}</td>
                    <td>{f.key}</td>
                    <td>
                      {
                        state.mappings.filter(
                          (m) =>
                            m.assetId === a.id &&
                            m.fieldPath === f.path &&
                            knowledgeView(state, reader).some(
                              (k) => k.id === m.knowledgeId,
                            ),
                        ).length
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!a.fields.length && (
            <StateNotice title="No column metadata supplied">
              Metric expressions are in the metric editor. No source samples are
              available.
            </StateNotice>
          )}
        </Panel>
      )}
      {tab === "Semantic mappings" && (
        <MappingWorkbench
          startOpen={mappingStart > 0}
          onStarted={() => setMappingStart(0)}
          assetId={a.id}
          onObject={onObject}
        />
      )}{" "}
      {tab === "Lineage" && <GraphScreen assetId={a.id} onObject={onObject} />}{" "}
      {tab === "Access" && <Access providerId={a.providerId} />}{" "}
      {tab === "Changes" && <Changes targetId={a.id} />}{" "}
      {tab === "Metric editor" && <MetricEditor assetId={a.id} />}{" "}
      {column && (
        <Modal
          wide
          title={`Column · ${column.path}`}
          description={`${a.providerId} / ${a.nativeId}`}
          onClose={() => setColumn(null)}
        >
          <KeyValue
            items={{
              "Containing asset": a.name,
              "Field path": column.path,
              Type: column.type,
              Nullable: column.nullable ? "Yes" : "No",
              Comment: column.comment,
              Classification: column.classification,
              "Declared key role": column.key,
              Evidence: `${a.sourceRevision} · ${new Date(a.observedAt).toISOString()}`,
            }}
          />
          <MappingWorkbench
            assetId={a.id}
            fieldPath={column.path}
            onObject={(id) => {
              setColumn(null);
              onObject(id);
            }}
          />
        </Modal>
      )}
      {proposal && target && (
        <ProposalDialog
          targetId={a.id}
          field={proposal}
          initial={target.content[proposal]}
          onClose={() => setProposal(null)}
          onSaved={() => {
            setProposal(null);
            setTab("Changes");
          }}
        />
      )}
    </>
  );
}
export function MappingWorkbench({
  assetId,
  fieldPath,
  onObject,
  startOpen = false,
  onStarted,
}: {
  assetId?: string;
  fieldPath?: string;
  startOpen?: boolean;
  onStarted?: () => void;
  onObject: (id: string) => void;
}) {
  const { state, reader, command } = useRepo();
  const [open, setOpen] = useState(false),
    [asset, setAsset] = useState(assetId || "customers"),
    [field, setField] = useState(fieldPath || ""),
    [knowledge, setKnowledge] = useState("customer-entity"),
    [attribute, setAttribute] = useState("identity"),
    [type, setType] = useState("concept attribute"),
    [scope, setScope] = useState("Enterprise"),
    [evidence, setEvidence] = useState(""),
    [from, setFrom] = useState("2026-10-01"),
    [to, setTo] = useState("");
  const mappingGuard = useDraftGuard(
    open &&
      (!!evidence ||
        asset !== (assetId || "customers") ||
        field !== (fieldPath || "") ||
        knowledge !== "customer-entity" ||
        attribute !== "identity" ||
        type !== "concept attribute" ||
        scope !== "Enterprise" ||
        from !== "2026-10-01" ||
        !!to),
    "Semantic mapping",
    () => setOpen(false),
  );
  useEffect(() => {
    if (startOpen) {
      setOpen(true);
      onStarted?.();
    }
  }, [startOpen]);
  const list = state.mappings.filter(
    (m) =>
      (!assetId || m.assetId === assetId) &&
      (fieldPath === undefined || m.fieldPath === fieldPath) &&
      knowledgeView(state, reader).some((k) => k.id === m.knowledgeId) &&
      assetView(state, reader).some((a) => a.id === m.assetId),
  );
  const a = assetView(state, reader).find((a) => a.id === asset);
  return (
    <Panel
      title="Semantic mappings"
      action={
        <Button icon={Link} onClick={() => setOpen(true)}>
          Create mapping
        </Button>
      }
    >
      {list.map((m) => (
        <div className="mapping-card" key={m.id}>
          <div className="inline">
            <Status value={m.status} />
            {list.filter(
              (x) => x.assetId === m.assetId && x.fieldPath === m.fieldPath,
            ).length > 1 && <Status value="Competing mappings" />}
          </div>
          <button className="text-link" onClick={() => onObject(m.knowledgeId)}>
            {state.knowledge.find((k) => k.id === m.knowledgeId)?.name} ·{" "}
            {m.attribute}
          </button>
          <p>
            {state.assets.find((a) => a.id === m.assetId)?.name}
            {m.fieldPath ? ` / ${m.fieldPath}` : ""}
          </p>
          <small>
            {m.type} · {m.scope} · {m.evidence}
          </small>
          <div className="inline">
            <MappingReviewActions
              status={m.status}
              onReview={async () => await command(
                "mapping.review", { id: m.id },
                "Mapping reviewed; physical correctness remains unverified.",
              )}
              onRemove={async () => await command(
                "mapping.remove", { id: m.id }, "Draft mapping removed.",
              )}
            />
          </div>
        </div>
      ))}
      {!list.length && (
        <StateNotice title="No mapping supplied">
          Missing mapping evidence is unknown, not proof of no semantic
          relationship.
        </StateNotice>
      )}
      {open && (
        <Modal
          wide
          title="Create a draft mapping"
          onClose={() => mappingGuard.attempt(() => setOpen(false))}
        >
          <div className="form-grid">
            <Select
              label="UOL object"
              value={knowledge}
              onChange={setKnowledge}
              options={knowledgeView(state, reader).map((k) => ({
                value: k.id,
                label: `${k.name} · ${k.scope}`,
              }))}
            />
            <TextInput
              label="Concept attribute / dimension / input"
              value={attribute}
              onChange={setAttribute}
            />
            <Select
              label="Source asset"
              value={asset}
              onChange={(v) => {
                setAsset(v);
                setField("");
              }}
              options={assetView(state, reader)
                .filter((a) => !["catalog", "schema"].includes(a.type))
                .map((a) => ({
                  value: a.id,
                  label: `${a.name} (${a.providerId})`,
                }))}
            />
            <Select
              label="Field path"
              value={field}
              onChange={setField}
              options={[
                { value: "", label: "Whole asset" },
                ...(a?.fields || []).map((f) => ({
                  value: f.path,
                  label: f.path,
                })),
                ...(a?.type === "metric_view"
                  ? [
                      {
                        value: "active_customers",
                        label: "active_customers (measure)",
                      },
                    ]
                  : []),
              ]}
            />
            <Select
              label="Mapping type"
              value={type}
              onChange={setType}
              options={opts([
                "concept attribute",
                "dimension",
                "metric input",
                "implemented by",
              ])}
            />
            <TextInput
              label="Business scope"
              value={scope}
              onChange={setScope}
            />
            <TextInput label="Valid from" value={from} onChange={setFrom} />
            <TextInput
              label="Valid to (optional)"
              value={to}
              onChange={setTo}
            />
          </div>
          <TextInput
            label="Evidence and rationale"
            value={evidence}
            onChange={setEvidence}
            area
          />
          <Button
            variant="primary"
            onClick={async () => {
              if (
                await command(
                  "mapping.save",
                  {
                    mapping: {
                      knowledgeId: knowledge,
                      attribute,
                      assetId: asset,
                      fieldPath: field,
                      type,
                      scope,
                      evidence,
                      validFrom: from,
                      validTo: to || undefined,
                    },
                  },
                  "Draft mapping saved.",
                )
              ) {
                mappingGuard.markClean();
                setOpen(false);
              }
            }}
          >
            Save draft mapping
          </Button>
        </Modal>
      )}
    </Panel>
  );
}
export function Access({ providerId }: { providerId: string }) {
  const { state, reader } = useRepo();
  const attempt = useNavigationGuard();
  const p = state.providers.find((p) => p.id === providerId)!;
  return (
    <Panel title="Permission and capability matrix">
      <KeyValue
        items={{
          Reader: reader,
          "Provider instance": p.id,
          Workspace: p.workspace,
          Metastore: p.metastore,
        }}
      />
      <table>
        <thead>
          <tr>
            <th>Operation</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(p.capabilities).map(([key, value]) => (
            <tr key={key}>
              <td>
                {
                  (
                    {
                      discovery: "Metadata discovery",
                      inspection: "Metadata inspection",
                      data: "Source-data access",
                      modification: "Metadata modification",
                      management: "Target management",
                    } as any
                  )[key]
                }
              </td>
              <td>
                <Status
                  value={
                    reader === "restricted" &&
                    ["modification", "management"].includes(key)
                      ? "denied"
                      : value
                  }
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <PermissionSummary />
      <p className="muted">
        No Grant or Revoke actions. Actual Azure privileges depend on the object
        and account; these outcomes are explicit fixtures.
      </p>
    </Panel>
  );
}
function ProjectionEditor() {
  const { state, reader, command, simulation } = useRepo();
  const [id, setId] = useState(
      state.domains.find((d) => d.id === "retention")?.id ||
        state.domains[0]?.id ||
        "",
    ),
    [choice, setChoice] = useState("ancestor");
  if (!state.domains.some((d) => d.id === id))
    return <StateNotice title="No domain available for projection" />;
  const pr = projection(state, id, choice);
  return (
    <>
      <Title
        eyebrow="UC-09 / Discover"
        title="Project meaning, preserve identity."
        description="UOL supports deep ownership hierarchies. Native domains support a domain and one subdomain level."
      />
      <div className="native-domain-cards">
        {["Customer", "Finance", "Operations"].map((name) => (
          <Panel key={name} title={name}>
            <TreeStructure size={24} />
            <p>
              {name === "Customer"
                ? "Lifecycle"
                : name === "Finance"
                  ? "Receivables"
                  : "Service delivery"}
            </p>
            <small>Simulated native domain</small>
          </Panel>
        ))}
      </div>
      <div className="form-grid">
        <Select
          label="UOL domain"
          value={id}
          onChange={setId}
          options={state.domains.map((d) => ({ value: d.id, label: d.name }))}
        />
        <Select
          label="Projection strategy"
          value={choice}
          onChange={setChoice}
          options={[
            {
              value: "ancestor",
              label: "Associate with existing native ancestor",
            },
            {
              value: "flatten",
              label: "Flatten deep path into subdomain label",
            },
            {
              value: "uol-only",
              label: "Retain additional hierarchy only in UOL",
            },
          ]}
        />
      </div>
      <Panel title="Projection diff">
        <KeyValue
          items={{
            "Original UOL identity": pr.uolId,
            "Full UOL path": pr.fullPath,
            "Native domain": pr.nativeDomain || "No native assignment",
            "Native subdomain": pr.nativeSubdomain || "None",
            "Depth beyond native hierarchy": pr.lostDepth,
            "Naming collision": pr.collision
              ? "Review required"
              : "No collision in fixtures",
            "Actual Page ownership":
              state.pages[0]?.domain || "No Page supplied",
          }}
        />
        <Json value={pr.tags} />
        <Callout>
          Parent and subdomain tags are explicit. Multiple native asset
          memberships are allowed; each Page retains one domain/subdomain.
          Projection never moves the UOL Page.
        </Callout>
        <div className="inline">
          <Button
            icon={Download}
            onClick={() =>
              downloadJSON(exportEnvelope(pr, simulation), "uol-domain-projection.json")
            }
          >
            Export projection plan
          </Button>
          <Button
            onClick={async () =>
              await command(
                "projection.propose",
                { domainId: id, choice },
                "Projection proposal prepared.",
              )
            }
          >
            Prepare projection proposal
          </Button>
        </div>
      </Panel>
      <Panel title="Asset memberships">
        {assetView(state, reader)
          .filter(
            (a) =>
              a.domainIds.includes(id) || a.tags.domain === pr.nativeDomain,
          )
          .map((a) => (
            <div className="mini-row" key={a.id}>
              <span>{a.name}</span>
              <span>
                {Object.entries(a.tags)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ")}
              </span>
            </div>
          ))}
      </Panel>
    </>
  );
}
