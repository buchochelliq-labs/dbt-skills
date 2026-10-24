import React, { useState } from "react";
import { stringify, parse } from "yaml";
import { Download } from "@phosphor-icons/react";
import { useRepo } from "./store";
import { assetView, knowledgeView, exportEnvelope } from "./services";
import { validateMetric } from "./nativeValidation";
import {
  Panel,
  Title,
  Button,
  Status,
  TextInput,
  Select,
  opts,
  Json,
  Callout,
  Tabs,
  StateNotice,
  KeyValue,
  downloadJSON,
} from "./components";
import { useDraftGuard } from "./draftGuard";
import { ChangeDiff } from "./ChangesScreen";
export function MetricEditor({ assetId }: { assetId: string }) {
  const { state, reader, command, simulation } = useRepo();
  const t = state.targets.find((t) => t.id === assetId)!;
  const origins = knowledgeView(state, reader);
  const [originId, setOriginId] = useState(
    (simulation
      ? assetId === "mrr-view"
        ? "mrr"
        : "active-customers"
      : state.assets
          .find((a) => a.id === assetId)
          ?.knowledgeIds.find((id) => origins.some((k) => k.id === id))) ||
      origins[0]?.id ||
      "",
  );
  const initial = t.content.yaml || {
    version: "1.1",
    source: "finance.core.accounts",
    fields: [{ name: "month", expr: "accounting_month" }],
    measures: [
      {
        name: "monthly_recurring_revenue",
        expr: "SUM(normalised_monthly_recurring_charge)",
      },
    ],
  };
  const [expectedRevision] = useState(t.revision);
  const [text, setText] = useState(stringify(initial)),
    [mode, setMode] = useState("Form"),
    [runtime, setRuntime] = useState("17.3"),
    [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [accepted, setAccepted] = useState<string | null>(null);
  const guard = useDraftGuard(
    saving || text !== (accepted ?? stringify(initial)),
    "Metric definition",
    () => setText(stringify(initial)),
  );
  const check = validateMetric(text, runtime);
  const v = check.value;
  function edit(key: string, value: any) {
    setText(stringify({ ...v, [key]: value }));
    setPreview(false);
  }
  function editMeasure(index: number, key: string, value: any) {
    const measures = structuredClone(v.measures);
    measures[index][key] = value;
    edit("measures", measures);
  }
  return (
    <fieldset
      disabled={saving}
      style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
    >
      <Title
        eyebrow="UC-05 / Metric view"
        title="Define the metric, not a result."
        description="Native YAML 1.1 with a validated Runtime 17.3 subset. UOL annotations remain separate."
      />
      <div className="inline">
        <Status
          value={
            text === stringify(initial)
              ? "Imported source metadata"
              : "Unsaved edits"
          }
        />
        <Select
          label="Target runtime"
          value={runtime}
          onChange={setRuntime}
          options={opts(["16.4", "17.3", "18.1"])}
        />
      </div>
      <Tabs items={["Form", "YAML"]} value={mode} onChange={setMode} />
      {mode === "YAML" ? (
        <TextInput
          label="Native metric YAML"
          value={text}
          onChange={(v) => {
            setText(v);
            setPreview(false);
          }}
          area
        />
      ) : v && typeof v === "object" && !check.errors.length ? (
        <>
          <div className="form-grid">
            <TextInput
              label="Source table / view / semantic SQL definition"
              value={v.source || ""}
              onChange={(x) => edit("source", x)}
            />
            <TextInput
              label="Filter expression"
              value={v.filter || ""}
              onChange={(x) => edit("filter", x)}
            />
            <TextInput
              label="Native comment"
              value={v.comment || ""}
              onChange={(x) => edit("comment", x)}
            />
          </div>
          {Array.isArray(v.measures) &&
            v.measures.map((m: any, i: number) => (
              <Panel key={i} title={`Measure ${i + 1}`}>
                <div className="form-grid">
                  <TextInput
                    label="Measure name"
                    value={m.name || ""}
                    onChange={(x) => editMeasure(i, "name", x)}
                  />
                  <TextInput
                    label="Expression"
                    value={m.expr || ""}
                    onChange={(x) => editMeasure(i, "expr", x)}
                  />
                  <TextInput
                    label="Display name"
                    value={m.display_name || ""}
                    onChange={(x) => editMeasure(i, "display_name", x)}
                  />
                  <TextInput
                    label="Synonyms (comma separated)"
                    value={(m.synonyms || []).join(", ")}
                    onChange={(x) =>
                      editMeasure(
                        i,
                        "synonyms",
                        x
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                      )
                    }
                  />
                </div>
                <Json
                  value={m.format || { note: "No native formatting supplied" }}
                />
              </Panel>
            ))}
          <Panel title="Fields / dimensions & joins">
            <Json
              value={{ fields: v.fields || v.dimensions, joins: v.joins }}
            />
            <Button onClick={() => setMode("YAML")}>
              Edit fields, joins & formatting in YAML
            </Button>
          </Panel>
        </>
      ) : (
        <StateNotice kind="error" title="Invalid YAML">
          Switch to YAML to repair the definition.
        </StateNotice>
      )}
      <Panel title="Validation">
        {check.errors.length ? (
          check.errors.map((e, i) => (
            <p role="alert" className="error-text" key={i}>
              {e}
            </p>
          ))
        ) : (
          <Status value="Valid supported structure" />
        )}
        <p className="muted">
          Structure and declared feature gates only. No SQL execution,
          expression correctness or native compilation is claimed.
        </p>
      </Panel>
      <Select
        label="UOL origin"
        value={originId}
        onChange={setOriginId}
        options={origins.map((k) => ({ value: k.id, label: k.name }))}
      />
      <div className="inline">
        <Button
          disabled={!!check.errors.length}
          onClick={() => setPreview(true)}
        >
          Validate & preview exact change
        </Button>
        {preview && !check.errors.length && originId && (
          <Button
            variant="primary"
            onClick={async () => {
              if (saving) return;
              setSaving(true);
              const result = await command(
                "proposal.create",
                {
                  proposal: {
                    originId,
                    targetId: assetId,
                    field: "yaml",
                    after: check.value,
                    reason:
                      "Reviewed metric semantics and native agent metadata.",
                    expectedRevision,
                  },
                },
                "Metric proposal saved. Review it in Changes.",
              );
              setSaving(false);
              if (result) {
                setAccepted(text);
                guard.markClean();
              }
            }}
          >
            Prepare metric proposal
          </Button>
        )}
      </div>
      {preview && <ChangeDiff before={t.content.yaml ?? null} after={v} />}
    </fieldset>
  );
}
export function PagesEditor() {
  const { state } = useRepo();
  if (!state.pages.length)
    return (
      <StateNotice title="No Pages yet">
        Create knowledge with type Page under Domains, or import Page metadata,
        to start a draft and prepare a reviewed handoff.
      </StateNotice>
    );
  return <PagesEditorContent />;
}
function PagesEditorContent() {
  const { state, reader, command, simulation } = useRepo();
  const [selected, setSelected] = useState(state.pages[0].id),
    [draft, setDraft] = useState(structuredClone(state.pages[0]));
  const [mode, setMode] = useState("Edit");
  const saved = state.pages.find((p) => p.id === selected)!;
  const destination = state.targets.find(
    (t) =>
      t.kind === "page" &&
      (t.id === selected ||
        t.content.page?.id === selected ||
        (simulation &&
          selected === "lifecycle-page" &&
          t.id === "page-lifecycle")),
  );
  const [saving, setSaving] = useState(false);
  const [accepted, setAccepted] = useState<string | null>(null);
  const guard = useDraftGuard(
    saving || JSON.stringify(draft) !== (accepted ?? JSON.stringify(saved)),
    "Page draft",
    () => setDraft(structuredClone(saved)),
  );
  const pageError =
    !draft.name.trim() || !draft.body.trim() || !draft.owner.trim();
  return (
    <fieldset
      disabled={saving}
      style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
    >
      <Title
        eyebrow="UC-10 / Native Pages handoff"
        title="Knowledge, ready for human review."
        description="Related assets identify technical context. Sources retain supporting evidence."
      />
      <Select
        label="Page"
        value={selected}
        onChange={(id) =>
          guard.attempt(() => {
            setAccepted(null);
            setSelected(id);
            setDraft(structuredClone(state.pages.find((p) => p.id === id)!));
          })
        }
        options={state.pages.map((p) => ({ value: p.id, label: p.name }))}
      />
      <Tabs items={["Edit", "Preview"]} value={mode} onChange={setMode} />
      {mode === "Edit" ? (
        <>
          <div className="form-grid">
            <TextInput
              label="Page title"
              value={draft.name}
              onChange={(name) => setDraft({ ...draft, name })}
            />
            <TextInput
              label="Owner"
              value={draft.owner}
              onChange={(owner) => setDraft({ ...draft, owner })}
            />
            <Select
              label="One UOL ownership domain"
              value={draft.domain}
              onChange={(domain) => setDraft({ ...draft, domain })}
              options={state.domains.map((d) => ({
                value: d.id,
                label: d.name,
              }))}
            />
            <Select
              label={
                simulation
                  ? "Simulated Page lifecycle"
                  : "Page lifecycle metadata"
              }
              value={draft.state}
              onChange={(v) => setDraft({ ...draft, state: v as any })}
              options={opts(["Draft", "Published", "Archived"])}
            />
            <TextInput
              label="Synonyms"
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
          </div>
          <TextInput
            label="Summary"
            value={draft.summary}
            onChange={(summary) => setDraft({ ...draft, summary })}
          />
          <TextInput
            label="Page body"
            value={draft.body}
            onChange={(body) => setDraft({ ...draft, body })}
            area
          />
          <Panel title="Related assets">
            {assetView(state, reader)
              .filter((a) => ["table", "view", "metric_view"].includes(a.type))
              .map((a) => (
                <label className="check" key={a.id}>
                  <input
                    type="checkbox"
                    checked={draft.relatedAssets.includes(a.id)}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        relatedAssets: e.target.checked
                          ? [...draft.relatedAssets, a.id]
                          : draft.relatedAssets.filter((id) => id !== a.id),
                      })
                    }
                  />
                  {a.name}
                </label>
              ))}
          </Panel>
          <TextInput
            label="Evidence Sources (one reference per line)"
            value={draft.sources.join("\n")}
            onChange={(v) =>
              setDraft({ ...draft, sources: v.split("\n").filter(Boolean) })
            }
            area
          />
        </>
      ) : (
        <Panel title={draft.name}>
          <Status value={draft.state} />
          <p>{draft.summary}</p>
          <p className="definition-lead small-lead">{draft.body}</p>
          <KeyValue
            items={{
              Domain: state.domains.find((d) => d.id === draft.domain)?.name,
              Owner: draft.owner,
              "Related assets": draft.relatedAssets
                .map(
                  (id) =>
                    assetView(state, reader).find((a) => a.id === id)?.name,
                )
                .filter(Boolean)
                .join(", "),
              Sources: draft.sources.join(", "),
            }}
          />
        </Panel>
      )}
      <Callout>
        Direct Page publication is unsupported. Native bulk import includes
        human review and creates drafts. This handoff draft is separate from
        approved UOL knowledge used for agent context; native Genie One can use
        an owner's draft Pages.
      </Callout>
      {pageError && (
        <p role="alert">
          Title, owner and body are required before saving or exporting.
        </p>
      )}
      {!destination && (
        <StateNotice title="No Page destination observed">
          Synchronize configured metadata providers to prepare a reviewed
          handoff. You can save this draft and export it for review now.
        </StateNotice>
      )}
      <div className="inline">
        <Button
          disabled={pageError}
          onClick={async () => {
            if (saving) return;
            setSaving(true);
            const result = await command(
              "page.save",
              { page: draft },
              "Page draft saved. Native state unchanged.",
            );
            setSaving(false);
            if (result) {
              setAccepted(JSON.stringify(draft));
              guard.markClean();
            }
          }}
        >
          {simulation ? "Save session draft" : "Save draft"}
        </Button>
        <Button
          variant="primary"
          disabled={pageError || !destination}
          onClick={async () => {
            if (saving || !destination) return;
            setSaving(true);
            const result = await command(
              "proposal.create",
              {
                proposal: {
                  originId: selected,
                  targetId: destination!.id,
                  field: "page",
                  after: draft,
                  reason: "Human-reviewed Pages import handoff.",
                },
              },
              "Page proposal saved; review before exporting delivery handoff.",
            );
            setSaving(false);
            if (result) {
              setAccepted(JSON.stringify(draft));
              guard.markClean();
            }
          }}
        >
          Prepare Page handoff
        </Button>
        <Button
          icon={Download}
          disabled={pageError}
          onClick={() =>
            downloadJSON(
              exportEnvelope({
                reviewRequired: true,
                page: {
                  ...draft,
                  relatedAssets: draft.relatedAssets.filter((id) =>
                    assetView(state, reader).some((a) => a.id === id),
                  ),
                },
                manualStep:
                  "Review source content in Pages bulk import; resulting Pages are drafts.",
              }, simulation),
              "uol-page-review-draft.json",
            )
          }
        >
          Export review draft
        </Button>
      </div>
    </fieldset>
  );
}
export function GenieEditor() {
  const { state } = useRepo();
  if (!state.targets.some((target) => target.kind === "genie"))
    return (
      <StateNotice title="No Genie targets yet">
        Import a complete Genie configuration to prepare a reviewed proposal.
      </StateNotice>
    );
  return <GenieEditorContent />;
}
function GenieEditorContent() {
  const { state, reader, command, simulation } = useRepo();
  const targets = state.targets.filter((t) => t.kind === "genie");
  const origins = knowledgeView(state, reader);
  const [originId, setOriginId] = useState(
    simulation && origins.some((k) => k.id === "active-customer")
      ? "active-customer"
      : origins[0]?.id || "",
  );
  const [targetId, setTarget] = useState(targets[0].id);
  const target = targets.find((t) => t.id === targetId)!;
  const [snapshot, setSnapshot] = useState(structuredClone(target)),
    [text, setText] = useState(
      target.content.serialized_space.instructions.text_instructions[0].content.join(
        "\n",
      ),
    ),
    [full, setFull] = useState(
      JSON.stringify(target.content.serialized_space, null, 2),
    ),
    [mode, setMode] = useState("Instructions"),
    [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [accepted, setAccepted] = useState<string | null>(null);
  const guard = useDraftGuard(
    full !==
      (accepted ?? JSON.stringify(snapshot.content.serialized_space, null, 2)),
    "Genie configuration",
    () => setFull(JSON.stringify(snapshot.content.serialized_space, null, 2)),
  );
  let parsed: any,
    err = "";
  try {
    parsed = JSON.parse(full);
    if (
      parsed.version !== 2 ||
      ![parsed.data_sources, parsed.instructions, parsed.config].every(
        (x) => x && typeof x === "object" && !Array.isArray(x),
      ) ||
      !Array.isArray(parsed.instructions?.text_instructions) ||
      !Array.isArray(parsed.instructions?.text_instructions?.[0]?.content) ||
      parsed.instructions.text_instructions[0].content.some(
        (x: any) => typeof x !== "string",
      )
    )
      err = "Complete version 2 configuration required.";
  } catch {
    err = "Configuration is not valid JSON.";
  }
  function modify(v: string) {
    setText(v);
    if (err) return;
    const config = structuredClone(parsed);
    config.instructions.text_instructions[0].content = v.split("\n");
    setFull(JSON.stringify(config, null, 2));
    setPreview(false);
  }
  return (
    <fieldset
      disabled={saving}
      style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
    >
      <Title
        eyebrow="UC-11 / Genie Agent & Space"
        title="Context for the native experience."
        description="Configuration only. No conversations, query execution, benchmark results or invented authority scores."
      />
      <Select
        label="UOL origin"
        value={originId}
        onChange={setOriginId}
        options={origins.map((k) => ({ value: k.id, label: k.name }))}
      />
      <Select
        label="Destination target"
        value={targetId}
        onChange={(id) =>
          guard.attempt(() => {
            setAccepted(null);
            setTarget(id);
            const t = targets.find((t) => t.id === id)!;
            setSnapshot(structuredClone(t));
            setFull(JSON.stringify(t.content.serialized_space, null, 2));
            setText(
              t.content.serialized_space.instructions.text_instructions[0].content.join(
                "\n",
              ),
            );
          })
        }
        options={targets.map((t) => ({ value: t.id, label: t.name }))}
      />
      <div className="inline">
        <Status
          value={
            full === JSON.stringify(snapshot.content.serialized_space, null, 2)
              ? "Imported source metadata"
              : "Unsaved configuration"
          }
        />
        <span>
          Pinned ETag revision {snapshot.revision} · current {target.revision}
        </span>
        <Button
          onClick={() =>
            guard.attempt(() => {
              setAccepted(null);
              setSnapshot(structuredClone(target));
              setFull(JSON.stringify(target.content.serialized_space, null, 2));
              setText(
                target.content.serialized_space.instructions.text_instructions[0].content.join(
                  "\n",
                ),
              );
              setPreview(false);
            })
          }
        >
          Reload complete target
        </Button>
      </div>
      <Tabs
        items={["Instructions", "Complete configuration"]}
        value={mode}
        onChange={setMode}
      />
      {mode === "Instructions" ? (
        <>
          <TextInput
            label="Native text instructions"
            value={
              err
                ? ""
                : parsed.instructions.text_instructions[0].content.join("\n")
            }
            onChange={modify}
            area
          />
          <div className="two-columns">
            <Panel title="Referenced tables & metric views">
              {(Array.isArray(parsed?.data_sources?.tables)
                ? parsed.data_sources.tables
                : []
              ).map((t: any, i: number) => (
                <p key={i}>
                  {t.identifier || t.table_name || t.name || "Declared table"}
                </p>
              ))}
              <details>
                <summary>Complete source metadata</summary>
                <Json value={parsed?.data_sources} />
              </details>
            </Panel>
            <Panel title="Declared joins">
              <Json value={parsed?.instructions?.join_specs} />
            </Panel>
          </div>
          <Panel title="Sanitized example SQL definitions">
            <Json value={parsed?.instructions?.example_question_sqls} />
            <small>Definitions only; never executed.</small>
          </Panel>
          <Panel title="Benchmark definitions">
            <Json value={parsed?.benchmarks} />
            <small>Expected semantic checks only; no benchmark results.</small>
          </Panel>
        </>
      ) : (
        <TextInput
          label="Complete serialized_space JSON"
          value={full}
          onChange={(v) => {
            setFull(v);
            setPreview(false);
          }}
          area
        />
      )}
      <Callout>
        serialized_space replaces the full configuration. This editor starts
        from a complete target snapshot and preserves other sections.{" "}
        {simulation
          ? "The mocked ETag blocks concurrent changes."
          : "The pinned target revision is checked before preparing the proposal."}{" "}
        Live schema validation remains adapter work.
      </Callout>
      {err && <StateNotice title={err} kind="error" />}
      <div className="inline">
        <Button disabled={!!err} onClick={() => setPreview(true)}>
          Preview replacement
        </Button>
        {preview && !err && originId && (
          <Button
            variant="primary"
            onClick={async () => {
              if (saving) return;
              setSaving(true);
              const result = await command(
                "proposal.create",
                {
                  proposal: {
                    originId,
                    targetId,
                    field: "serialized_space",
                    after: parsed,
                    reason:
                      "Update instructions while preserving unrelated complete configuration.",
                    expectedRevision: snapshot.revision,
                  },
                },
                "Genie proposal prepared; review and delivery remain separate.",
              );
              setSaving(false);
              if (result) {
                setAccepted(full);
                guard.markClean();
              }
            }}
          >
            Prepare Genie proposal
          </Button>
        )}
      </div>
      {preview && (
        <ChangeDiff before={snapshot.content.serialized_space} after={parsed} />
      )}
    </fieldset>
  );
}
