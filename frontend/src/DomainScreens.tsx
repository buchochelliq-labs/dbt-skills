import { useDraftGuard } from "./draftGuard";
import React, { useState } from "react";
import {
  Plus,
  ArrowRight,
  GitBranch,
  PencilSimple,
  Sparkle,
} from "@phosphor-icons/react";
import { useRepo } from "./store";
import { path, domainKnowledge, knowledgeView, inherited, ttl, domainEditError, comparableMeanings } from "./services";
import type { Knowledge, Domain } from "./contracts";
import {
  Panel,
  Title,
  Button,
  TypeIcon,
  Status,
  TextInput,
  Select,
  opts,
  Modal,
  KeyValue,
  Callout,
  Json,
  StateNotice,
  Tabs,
} from "./components";
export function Domains({
  domainId,
  selected,
  onDomain,
  onObject,
  onContext,
}: {
  domainId: string;
  selected: string | null;
  onDomain: (id: string) => void;
  onObject: (id: string | null) => void;
  onContext: (id?: string) => void;
}) {
  const { state, reader, command } = useRepo();
  const [tab, setTab] = useState("Knowledge"),
    [q, setQ] = useState(""),
    [type, setType] = useState("All"),
    [desc, setDesc] = useState(true),
    [edit, setEdit] = useState<"new" | "domain" | "knowledge" | null>(null),
    [compare, setCompare] = useState(false),
    [adding, setAdding] = useState(false),
    [reviewOnly, setReviewOnly] = useState(false);
  const d = state.domains.find((d) => d.id === domainId)!;
  const k = knowledgeView(state, reader).find((k) => k.id === selected);
  const meanings = comparableMeanings(state, reader);
  const domainItems = domainKnowledge(state, reader, d.id, desc);
  const list = domainItems.filter(
    (k) =>
      (!reviewOnly || k.status !== "Approved") &&
      (type === "All" || k.type === type) &&
      `${k.name} ${k.summary}`.toLowerCase().includes(q.toLowerCase()),
  );
  return (
    <>
      <div className="workspace-body">
        <div className="work-main">
          <div className="crumbs">
            {path(state, d.id).map((x) => (
              <button key={x.id} onClick={() => onDomain(x.id)}>
                {x.name}
                <span>/</span>
              </button>
            ))}
            {k && <span>{k.name}</span>}
          </div>
          {k ? (
            <>
              <Title
                eyebrow={`${k.type} · UOL definition`}
                title={k.name}
                action={
                  <Button icon={Sparkle} onClick={() => onContext(k.id)}>
                    Agent context
                  </Button>
                }
              />
              <div className="inline">
                <Status value={k.status} />
                <span>{k.origin} origin</span>
                <span>Revision {k.version}</span>
                <Button
                  icon={PencilSimple}
                  onClick={() => setEdit("knowledge")}
                >
                  Edit revision
                </Button>
              </div>
              <p className="definition-lead">{k.definition}</p>
              <div className="inline">
                <Button onClick={() => onObject(null)}>Back to domain</Button>
                {meanings.some(m => m.id === k.id) && (
                  <Button onClick={() => setCompare(true)}>
                    Compare meanings
                  </Button>
                )}
                {k.status !== "Approved" && reader === "steward" && (
                  <Button
                    variant="primary"
                    onClick={async () =>
                      await command(
                        "knowledge.approve",
                        { id: k.id },
                        "Approved for this scope; origin preserved.",
                      )
                    }
                  >
                    Approve definition
                  </Button>
                )}
              </div>
              <Panel title="Meaning & boundaries">
                <KeyValue
                  items={{
                    Scope: k.scope,
                    Grain: k.grain,
                    "Time interpretation":
                      k.scope === "Billing"
                        ? "Accounting period"
                        : k.scope === "Service"
                          ? "Reporting date"
                          : "Declared business validity",
                    "Primary ownership": path(state, k.domain)
                      .map((d) => d.name)
                      .join(" / "),
                    "Additional memberships": k.memberships
                      .map((id) => state.domains.find((d) => d.id === id)?.name)
                      .join(", "),
                    "Business-valid from": k.validFrom,
                    "Business-valid to": k.validTo || "Open ended",
                    Aliases: k.synonyms.join(", "),
                    Inclusions: k.logic,
                    Exclusions: k.exclusions,
                  }}
                />
              </Panel>
              {k.type === "Metric" && (
                <Panel title="Metric semantics">
                  <KeyValue
                    items={{
                      Formula: k.formula || <Status value="incomplete" />,
                      Unit: k.unit,
                      Aggregation: k.aggregation,
                      Dimensions: k.dimensions?.join(", "),
                    }}
                  />
                  <Callout>
                    Semantic expressions only. No computed metric values are
                    displayed.
                  </Callout>
                </Panel>
              )}
              <Panel title="Connected knowledge">
                {k.related
                  .filter((id) =>
                    knowledgeView(state, reader).some((x) => x.id === id),
                  )
                  .map((id) => {
                    const rel = state.knowledge.find((x) => x.id === id)!;
                    return (
                      <button
                        className="object-row"
                        key={id}
                        onClick={() => onObject(id)}
                      >
                        <TypeIcon type={rel.type} />
                        <span>
                          <strong>{rel.name}</strong>
                          <small>
                            {rel.scope} · {rel.type}
                          </small>
                        </span>
                        <ArrowRight />
                      </button>
                    );
                  })}
              </Panel>
              <Panel title="Revision history">
                {k.history.length ? (
                  k.history.map((r) => (
                    <div className="revision" key={r.revision}>
                      <Status value={r.status} />
                      <strong>
                        Revision {r.revision} · {r.origin}
                      </strong>
                      <p>{r.definition}</p>
                    </div>
                  ))
                ) : (
                  <p className="muted">
                    Imported revision {k.version}. Earlier history was not
                    supplied; no invented revision history.
                  </p>
                )}
              </Panel>
            </>
          ) : (
            <>
              <Title
                eyebrow="Domain workspace"
                title={d.name}
                description={d.description}
                action={
                  <Button
                    icon={Plus}
                    variant="primary"
                    onClick={() => setAdding(true)}
                  >
                    Add knowledge
                  </Button>
                }
              />
              <div className="stats domain-stats">
                <button
                  className={!reviewOnly && tab === "Knowledge" ? "chosen" : ""}
                  onClick={() => {
                    setReviewOnly(false);
                    setTab("Knowledge");
                  }}
                >
                  <strong>
                    {domainItems.length}
                  </strong>
                  <span>Knowledge objects</span>
                </button>
                <button onClick={() => setTab("Hierarchy")}>
                  <strong>
                    {state.domains.filter((x) => x.parent === d.id).length}
                  </strong>
                  <span>Subdomains</span>
                </button>
                <button
                  aria-pressed={reviewOnly}
                  className={reviewOnly ? "chosen" : ""}
                  onClick={() => {
                    setReviewOnly(!reviewOnly);
                    setTab("Knowledge");
                  }}
                >
                  <strong>
                    {
                      domainItems.filter((k) => k.status !== "Approved").length
                    }
                  </strong>
                  <span>Awaiting review</span>
                </button>
              </div>
              <Tabs
                items={["Knowledge", "Governance", "Hierarchy"]}
                value={tab}
                onChange={setTab}
              />
              {tab === "Knowledge" && (
                <>
                  <div className="toolbar">
                    <input
                      aria-label="Search domain knowledge"
                      placeholder="Search definitions, metrics, rules…"
                      value={q}
                      onChange={(e) => setQ(e.target.value)}
                    />
                    <select
                      aria-label="Filter knowledge type"
                      value={type}
                      onChange={(e) => setType(e.target.value)}
                    >
                      {[
                        "All",
                        "Concept",
                        "Business term",
                        "Metric",
                        "Rule",
                        "Page",
                      ].map((t) => (
                        <option key={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={desc}
                      onChange={(e) => setDesc(e.target.checked)}
                    />
                    Include descendant domains
                  </label>
                  <div className="object-list">
                    <div className="list-caption">
                      <span>KNOWLEDGE</span>
                      <span>REVIEW STATE</span>
                    </div>
                    {list.map((k) => (
                      <button
                        className="object-row"
                        key={k.id}
                        onClick={() => onObject(k.id)}
                      >
                        <TypeIcon type={k.type} />
                        <span>
                          <strong>
                            {k.name}{" "}
                            <span className="scope-label">{k.scope}</span>
                          </strong>
                          <small>{k.summary}</small>
                        </span>
                        <div>
                          <Status value={k.status} />
                          <small>{k.origin}</small>
                        </div>
                        <ArrowRight size={15} />
                      </button>
                    ))}
                  </div>
                  {!list.length && (
                    <StateNotice title="No knowledge in this view">
                      Change the search or include descendants.
                    </StateNotice>
                  )}
                  {meanings.length > 1 && <div className="review-note">
                    <Sparkle size={22} />
                    <div>
                      <strong>
                        Shared labels can have different meanings.
                      </strong>
                      <p>
                        Compare definitions before choosing agent context.
                      </p>
                    </div>
                    <Button onClick={() => setCompare(true)}>
                      Compare meanings
                    </Button>
                  </div>}
                </>
              )}
              {tab === "Governance" && <Governance domain={d} />}{" "}
              {tab === "Hierarchy" && (
                <>
                  <div className="inline">
                    <Button
                      variant="primary"
                      icon={Plus}
                      onClick={() => setEdit("new")}
                    >
                      New domain
                    </Button>
                  </div>
                  <Panel title="Stable identity">
                    <KeyValue
                      items={{
                        ID: d.id,
                        Path: path(state, d.id)
                          .map((d) => d.name)
                          .join(" / "),
                        Parent: d.parent || "Root",
                      }}
                    />
                    <Button onClick={() => setEdit("domain")}>
                      Rename or move domain
                    </Button>
                  </Panel>
                  {state.domains
                    .filter((x) => x.parent === d.id)
                    .map((x) => (
                      <button
                        className="object-row"
                        key={x.id}
                        onClick={() => onDomain(x.id)}
                      >
                        <GitBranch />
                        <span>
                          <strong>{x.name}</strong>
                          <small>{x.description}</small>
                        </span>
                        <ArrowRight />
                      </button>
                    ))}
                </>
              )}
            </>
          )}
        </div>
        <aside className="right-inspector">
          <div className="eyebrow">GOVERNANCE & EVIDENCE</div>
          <h2>{k ? "Definition evidence" : "Domain ownership"}</h2>
          <p className="muted">
            {k
              ? "Approval, origin and freshness are independent signals."
              : "Domain settings flow to descendants unless explicitly overridden."}
          </p>
          <Panel title="Accountability">
            <KeyValue
              items={{
                "Business owner":
                  k?.owner || String(inherited(state, d.id, "owner").value),
                "Technical owner": String(
                  inherited(state, d.id, "technicalOwner").value,
                ),
                Steward: String(inherited(state, d.id, "steward").value),
              }}
            />
          </Panel>
          {k ? (
            <Panel title="Provenance">
              <KeyValue
                items={{
                  "Semantic origin": k.originId,
                  Revision: k.version,
                  Provider: k.source,
                  "Source reference": k.sourcePath,
                  Approval: k.status,
                  Origin: k.origin,
                  Authority: "Not assessed",
                  Confidence: "Declared evidence",
                }}
              />
            </Panel>
          ) : (
            <details className="governance-disclosure">
              <summary>Cache policy & inheritance</summary>
              <Panel title="Effective cache policy">
                {state.providers.map((p) => (
                  <div className="mini-row" key={p.id}>
                    <span>{p.name}</span>
                    <strong>
                      {ttl(state, { domain: d.id } as Knowledge, p).hours}h
                    </strong>
                  </div>
                ))}
                <small className="muted">
                  Object → nearest domain → provider → workspace (24h). TTL is
                  not authority.
                </small>
              </Panel>
            </details>
          )}
          <Callout>
            Owning this domain does not confer source permissions.
          </Callout>
        </aside>
      </div>
      {adding && (
        <AddKnowledge
          domain={d.id}
          onClose={() => setAdding(false)}
          onSave={(id) => {
            setAdding(false);
            onObject(id);
          }}
        />
      )}
      {edit === "new" && (
        <DomainDialog
          parent={d.id}
          onClose={() => setEdit(null)}
          onSave={(id) => {
            setEdit(null);
            onDomain(id);
          }}
        />
      )}
      {edit === "domain" && (
        <DomainDialog
          domain={d}
          parent={d.parent}
          onClose={() => setEdit(null)}
          onSave={() => setEdit(null)}
        />
      )}{" "}
      {edit === "knowledge" && k && (
        <KnowledgeEditor object={k} onClose={() => setEdit(null)} />
      )}{" "}
      {compare && (
        <Modal
          wide
          title="Compare meanings"
          description="Review definitions that share a name within their business scopes."
          onClose={() => setCompare(false)}
        >
          <div className="comparison-grid">
            {meanings
              .map((k) => (
                <Panel key={k.id} title={k.scope}>
                  <Status value={k.status} />
                  <p className="definition-lead small-lead">{k.definition}</p>
                  <KeyValue
                    items={{
                      Grain: k.grain,
                      Time:
                        k.scope === "Service"
                          ? "Reporting date"
                          : "Accounting period",
                      Inclusions: k.logic,
                      Exclusions: k.exclusions,
                      Evidence: k.sourcePath,
                    }}
                  />
                  <Button
                    onClick={() => {
                      setCompare(false);
                      onObject(k.id);
                    }}
                  >
                    Open {k.scope} meaning
                  </Button>
                </Panel>
              ))}
          </div>
          {reader === "restricted" && (
            <StateNotice title="Some meanings are unavailable to this reader" />
          )}
        </Modal>
      )}
    </>
  );
}
function DomainDialog({
  domain,
  parent,
  onClose,
  onSave,
}: {
  domain?: Domain;
  parent: string | null;
  onClose: () => void;
  onSave: (id: string) => void;
}) {
  const { state, command } = useRepo();
  const [name, setName] = useState(domain?.name || ""),
    [p, setP] = useState(parent),
    [desc, setDesc] = useState(domain?.description || "");
  const validation = domainEditError(state, domain, name, p);
  const guard = useDraftGuard(
    name !== (domain?.name || "") ||
      p !== parent ||
      desc !== (domain?.description || ""),
    "Domain details",
  );
  return (
    <Modal
      title={domain ? "Rename or move domain" : "Create domain"}
      description="Identity and references survive renaming and moving. Cycles are rejected."
      onClose={() => guard.attempt(onClose)}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (validation) return;
          const result = await command<Domain>(
            domain ? "domain.update" : "domain.create",
            domain
              ? {
                  id: domain.id,
                  patch: {
                    name,
                    parent: p,
                    description: desc,
                  },
                }
              : { name, parent: p, description: desc },
            "Domain saved.",
          );
          if (result) {
            guard.markClean();
            onSave(result.id);
          }
        }}
      >
        <TextInput label="Domain name" value={name} onChange={setName} />
        {domain?.parent !== null && <Select
          label="Parent domain"
          value={p || ""}
          onChange={setP}
          options={state.domains.map((d) => ({
            value: d.id,
            label: path(state, d.id)
              .map((d) => d.name)
              .join(" / "),
          }))}
        />}
        <TextInput label="Description" value={desc} onChange={setDesc} area />
        {validation && (
          <div role="alert">
            <Callout tone="error">{validation}</Callout>
          </div>
        )}
        <div className="form-actions">
          <Button onClick={() => guard.attempt(onClose)} type="button">
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!!validation}>
            Save domain
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function Governance({ domain }: { domain: Domain }) {
  const { state, command } = useRepo();
  const [editing, setEditing] = useState<string | null>(null),
    [value, setValue] = useState("");
  const fields: [keyof Domain, string][] = [
    ["owner", "Business owner"],
    ["technicalOwner", "Technical owner"],
    ["steward", "Steward"],
    ["providerPolicy", "Provider policy"],
    ["ttl", "Cache TTL (hours)"],
  ];
  return (
    <Panel title="Governance & inheritance">
      {fields.map(([key, label]) => {
        const eff = inherited(state, domain.id, key);
        return (
          <div className="inheritance-row" key={key}>
            <div>
              <strong>{label}</strong>
              <p>
                {String(eff.value)} {key === "ttl" ? "hours" : ""}
              </p>
              <small>
                {key === "ttl" && eff.id === "workspace"
                  ? "No domain override; provider default applies before workspace."
                  : `From ${eff.origin}`}
              </small>
            </div>
            <div className="inline">
              <Button
                onClick={() => {
                  setEditing(key);
                  setValue(String(eff.value));
                }}
              >
                Override
              </Button>
              <Button
                disabled={domain[key] == null}
                onClick={async () =>
                  await command(
                    "domain.update",
                    { id: domain.id, patch: { [key]: null } },
                    "Reset to inherited.",
                  )
                }
              >
                Reset
              </Button>
            </div>
          </div>
        );
      })}
      {editing && (
        <Modal
          title="Override inherited setting"
          onClose={() => setEditing(null)}
        >
          <TextInput label={editing} value={value} onChange={setValue} />
          <Button
            variant="primary"
            onClick={async () => {
              const d = await command(
                "domain.update",
                {
                  id: domain.id,
                  patch: {
                    [editing]: editing === "ttl" ? Number(value) : value,
                  },
                },
                "Override saved.",
              );
              if (d) setEditing(null);
            }}
          >
            Save override
          </Button>
        </Modal>
      )}
    </Panel>
  );
}
export function KnowledgeEditor({
  object,
  onClose,
}: {
  object: Knowledge;
  onClose: () => void;
}) {
  const { state, command } = useRepo();
  const [draft, setDraft] = useState({ ...object });
  const guard = useDraftGuard(
    JSON.stringify(draft) !== JSON.stringify(object),
    "Knowledge revision",
  );
  const validDate = (value: string) => {
    const parsed = new Date(value);
    return (
      /^\d{4}-\d{2}-\d{2}$/.test(value) &&
      Number.isFinite(parsed.getTime()) &&
      parsed.toISOString().slice(0, 10) === value
    );
  };
  let validation = "";
  if (!draft.definition.trim()) validation = "Definition is required";
  else if (!state.domains.some((d) => d.id === draft.domain))
    validation = "Choose an existing ownership domain";
  else if (
    draft.memberships.some(
      (id) => id === draft.domain || !state.domains.some((d) => d.id === id),
    ) ||
    new Set(draft.memberships).size !== draft.memberships.length
  )
    validation =
      "Additional memberships must be unique existing domains, excluding the ownership domain";
  else if (!validDate(draft.validFrom))
    validation = "Business-valid from must be a real date in YYYY-MM-DD format";
  else if (draft.validTo && !validDate(draft.validTo))
    validation = "Business-valid to must be a real date in YYYY-MM-DD format";
  else if (draft.validTo && draft.validTo < draft.validFrom)
    validation = "Validity ends before it begins";
  const fields = [
    "definition",
    "scope",
    "grain",
    "owner",
    "validFrom",
    "validTo",
    ...(object.type === "Metric"
      ? ["formula", "unit", "aggregation", "logic", "exclusions"]
      : []),
  ];
  return (
    <Modal
      wide
      title={`Edit ${object.name}`}
      description="Saving creates a new draft revision. Approved history and inference origin are preserved."
      onClose={() => guard.attempt(onClose)}
    >
      <div className="form-grid">
        {fields.map((key) => (
          <TextInput
            key={key}
            label={key}
            value={String((draft as any)[key] || "")}
            area={["definition", "formula"].includes(key)}
            onChange={(v) => setDraft({ ...draft, [key]: v })}
          />
        ))}
        <TextInput
          label="Aliases (comma separated)"
          value={draft.synonyms.join(", ")}
          onChange={(v) =>
            setDraft({
              ...draft,
              synonyms: v
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
        />
        <TextInput
          label="Dimensions (comma separated)"
          value={(draft.dimensions || []).join(", ")}
          onChange={(v) =>
            setDraft({
              ...draft,
              dimensions: v
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
        />
        <Select
          label="Primary ownership domain"
          value={draft.domain}
          onChange={(v) =>
            setDraft({
              ...draft,
              domain: v,
              memberships: draft.memberships.filter((id) => id !== v),
            })
          }
          options={state.domains.map((d) => ({ value: d.id, label: d.name }))}
        />
      </div>
      {validation && (
        <p role="alert" className="error-text">
          {validation}
        </p>
      )}
      <Panel title="Additional domain memberships">
        <p>
          Primary ownership remains separate from these cross-domain
          memberships.
        </p>
        {state.domains
          .filter((d) => d.id !== draft.domain)
          .map((d) => (
            <label className="check" key={d.id}>
              <input
                type="checkbox"
                checked={draft.memberships.includes(d.id)}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    memberships: e.target.checked
                      ? [...draft.memberships, d.id]
                      : draft.memberships.filter((id) => id !== d.id),
                  })
                }
              />
              {d.name}
            </label>
          ))}
      </Panel>
      <Button
        variant="primary"
        disabled={!!validation}
        onClick={async () => {
          if (
            await command(
              "knowledge.revise",
              { id: object.id, patch: draft },
              "New draft revision saved.",
            )
          ) {
            guard.markClean();
            onClose();
          }
        }}
      >
        Save new revision
      </Button>
    </Modal>
  );
}

function AddKnowledge({
  domain,
  onClose,
  onSave,
}: {
  domain: string;
  onClose: () => void;
  onSave: (id: string) => void;
}) {
  const { command } = useRepo();
  const [name, setName] = useState(""),
    [definition, setDefinition] = useState(""),
    [type, setType] = useState("Concept");
  const guard = useDraftGuard(
    !!name || !!definition || type !== "Concept",
    "New knowledge",
  );
  return (
    <Modal title="Add knowledge" onClose={() => guard.attempt(onClose)}>
      <TextInput label="Name" value={name} onChange={setName} />
      <Select
        label="Knowledge type"
        value={type}
        onChange={setType}
        options={opts(["Concept", "Business term", "Metric", "Rule", "Page"])}
      />
      <TextInput
        label="Definition"
        value={definition}
        onChange={setDefinition}
        area
      />
      <Button
        variant="primary"
        onClick={async () => {
          const k = await command<Knowledge>(
            "knowledge.create",
            { domain, name, type, definition },
            "Draft created. Agent values remain withheld.",
          );
          if (k) {
            guard.markClean();
            onSave(k.id);
          }
        }}
      >
        Create draft
      </Button>
    </Modal>
  );
}
