import React, { useMemo, useState, useEffect } from "react";
import { useDraftGuard } from "./draftGuard";
import "./connections-graph.css";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  ReactFlowProvider,
  useReactFlow,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useRepo } from "./store";
import { knowledgeView, assetView } from "./services";
import {
  Panel,
  Title,
  Select,
  opts,
  KeyValue,
  Button,
  Status,
  Callout,
  StateNotice,
  Modal,
  TextInput,
} from "./components";
import type { Relationship } from "./contracts";
const colors: Record<string, string> = {
  membership: "#8c978e",
  is_a: "#8b63aa",
  part_of: "#bf8b50",
  business: "#1d7773",
  mapping: "#558aab",
  join: "#b99238",
  lineage: "#738494",
  dependency: "#b87798",
};
export function GraphScreen(props: {
  onObject: (id: string) => void;
  assetId?: string;
}) {
  return (
    <ReactFlowProvider>
      <GraphContent {...props} />
    </ReactFlowProvider>
  );
}
function GraphContent({
  onObject,
  assetId,
}: {
  onObject: (id: string) => void;
  assetId?: string;
}) {
  const { state, reader, command } = useRepo();
  const [editing, setEditing] = useState(false),
    [edgeLabel, setEdgeLabel] = useState(""),
    [edgeScope, setEdgeScope] = useState(""),
    [card, setCard] = useState("");
  const [filter, setFilter] = useState(assetId ? "all" : "business"),
    [q, setQ] = useState(""),
    [selected, setSelected] = useState(""),
    [edge, setEdge] = useState<Relationship | null>(null),
    [list, setList] = useState(false),
    [direction, setDirection] = useState("both");
  const [attempted, setAttempted] = useState(false);
  const dirty = !!(
    editing &&
    edge &&
    (edgeLabel !== edge.label ||
      edgeScope !== edge.scope ||
      card !== edge.cardinality)
  );
  const [saving, setSaving] = useState(false);
  const guard = useDraftGuard(dirty, "relationship declaration");
  const closeEditor = () => {
    if (!saving) guard.attempt(() => setEditing(false));
  };
  const errors = [
    !edgeLabel.trim() && "Enter a relationship label.",
    !edgeScope.trim() && "Enter the relationship scope.",
  ].filter(Boolean);
  const flow = useReactFlow();
  const ks = knowledgeView(state, reader),
    as = assetView(state, reader);
  const objects = [
    ...ks.map((k) => ({
      id: k.id,
      name: k.name === "Active customer" ? `${k.name} · ${k.scope}` : k.name,
      type: k.type,
    })),
    ...as
      .filter((a) => !["catalog", "schema"].includes(a.type))
      .map((a) => ({ id: a.id, name: a.name, type: a.type })),
    ...state.domains.map((d) => ({ id: d.id, name: d.name, type: "Domain" })),
  ];
  const valid = new Set(objects.map((o) => o.id));
  const edges: Relationship[] = [
    ...state.relationships,
    ...state.mappings
      .filter((m) => valid.has(m.knowledgeId) && valid.has(m.assetId))
      .map((m) => ({
        id: m.id,
        source: m.knowledgeId,
        target: m.assetId,
        type: "mapping" as const,
        label: m.fieldPath || m.type,
        scope: m.scope,
        cardinality: "unverified",
        provenance: m.evidence,
        approval: m.status,
      })),
    ...ks.map((k) => ({
      id: `member-${k.id}`,
      source: k.id,
      target: k.domain,
      type: "membership" as const,
      label: "owned by",
      scope: "Primary domain",
      cardinality: "one primary owner",
      provenance: "UOL governance",
      approval: k.status,
    })),
  ].filter((e) => valid.has(e.source) && valid.has(e.target));
  const focus = assetId || selected;
  const matches = edges.filter(
    (e) =>
      (filter === "all" ||
        (filter === "business" &&
          ["business", "is_a", "part_of", "dependency"].includes(e.type)) ||
        filter === e.type) &&
      (!assetId ||
        (direction === "upstream"
          ? e.target === assetId
          : direction === "downstream"
            ? e.source === assetId
            : e.source === assetId || e.target === assetId)),
  );
  const shown = objects.filter(
    (o) =>
      (matches.some((e) => e.source === o.id || e.target === o.id) ||
        o.id === assetId) &&
      (!q || o.name.toLowerCase().includes(q.toLowerCase())),
  );
  const ids = new Set(shown.map((o) => o.id));
  const shownEdges = matches.filter(
    (e) => ids.has(e.source) && ids.has(e.target),
  );
  const nodes = useMemo(
    () =>
      shown.map((o, i) => ({
        id: o.id,
        position: { x: (i % 3) * 270, y: Math.floor(i / 3) * 135 },
        data: {
          label: (
            <div className="graph-label">
              <small>{o.type}</small>
              <strong>{o.name}</strong>
            </div>
          ),
        },
        style: {
          borderColor: o.id === focus ? "#106c66" : "#ccdcd5",
          borderWidth: o.id === focus ? 2 : 1,
          width: 220,
          background: "#fff",
          borderRadius: 9,
        },
        ariaLabel: o.name,
      })),
    [shown.map((o) => o.id).join(","), focus],
  );
  const [liveNodes, setLiveNodes, onNodesChange] = useNodesState(nodes);
  useEffect(() => setLiveNodes(nodes), [nodes]);
  const obj = objects.find((o) => o.id === selected);
  return (
    <div className={assetId ? "" : "screen-pad"}>
      {!assetId && (
        <Title
          eyebrow="Knowledge graph"
          title="Meaning is connected."
          description="Explore business relationships, source mappings and declared dependencies."
        />
      )}
      <div className="toolbar">
        <input
          aria-label="Search graph"
          placeholder="Find a node…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          aria-label="Relationship type"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          {[
            "all",
            "business",
            "membership",
            "is_a",
            "part_of",
            "mapping",
            "join",
            "lineage",
            "dependency",
          ].map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        {assetId && (
          <select
            aria-label="Lineage direction"
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
          >
            {["both", "upstream", "downstream"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        )}
        <Button aria-pressed={list} onClick={() => setList(!list)}>
          {list ? "Show graph" : "Show accessible list"}
        </Button>
        {!list && <Button onClick={() => flow.fitView()}>Fit graph</Button>}
      </div>
      <p className="cg-view-summary" role="status">
        {shown.length} visible objects · {shownEdges.length} visible
        relationships.{" "}
        {list
          ? "Use Tab to select an object or relationship, then Enter to inspect it."
          : "Select an object or relationship to inspect its evidence."}
      </p>
      {!shown.length && (
        <StateNotice title="No visible objects match this view">
          Try another relationship type or clear your search. Missing coverage
          does not prove there are no dependencies.
          <Button
            onClick={() => {
              setQ("");
              setFilter("all");
              setDirection("both");
            }}
          >
            Reset graph filters
          </Button>
        </StateNotice>
      )}
      <div className="graph-workspace">
        <div>
          {list ? (
            <div className="graph-list">
              <h3>Relationships</h3>
              {!shownEdges.length && (
                <p className="muted">
                  No visible relationships match the current filters.
                </p>
              )}
              {shownEdges.map((e) => (
                <button
                  aria-pressed={edge?.id === e.id}
                  className="object-row"
                  key={e.id}
                  onClick={() => {
                    setEdge(e);
                    setSelected("");
                  }}
                >
                  <span>
                    <strong>
                      {objects.find((o) => o.id === e.source)?.name} →{" "}
                      {objects.find((o) => o.id === e.target)?.name}
                    </strong>
                    <small>
                      {e.type} · {e.label}
                    </small>
                  </span>
                </button>
              ))}
              <h3>Objects</h3>
              {shown.map((o) => (
                <Button
                  key={o.id}
                  aria-pressed={selected === o.id}
                  onClick={() => {
                    setSelected(o.id);
                    setEdge(null);
                  }}
                >
                  {o.name}
                </Button>
              ))}
            </div>
          ) : (
            <div className="graph-canvas">
              <ReactFlow
                nodes={liveNodes}
                onNodesChange={onNodesChange}
                edges={shownEdges.map((e) => ({
                  id: e.id,
                  source: e.source,
                  target: e.target,
                  label: e.label,
                  style: {
                    stroke: colors[e.type],
                    strokeDasharray: [
                      "mapping",
                      "dependency",
                      "membership",
                    ].includes(e.type)
                      ? "5 4"
                      : undefined,
                  },
                  markerEnd: {
                    type: MarkerType.ArrowClosed,
                    color: colors[e.type],
                  },
                }))}
                onNodeClick={(_, n) => {
                  setSelected(n.id);
                  setEdge(null);
                }}
                onEdgeClick={(_, e) => {
                  setEdge(shownEdges.find((x) => x.id === e.id)!);
                  setSelected("");
                }}
                fitView
                nodesDraggable
                nodesConnectable={false}
                minZoom={0.2}
              >
                <Background color="#cbd7d0" gap={22} />
                <Controls />
                <MiniMap />
              </ReactFlow>
            </div>
          )}
          <div className="graph-legend">
            {Object.entries(colors).map(([type, color]) => (
              <span key={type}>
                <i style={{ background: color }} />
                {type}
              </span>
            ))}
          </div>
        </div>
        <Panel
          title={
            edge
              ? "Relationship evidence"
              : obj
                ? "Selected object"
                : "Graph inspector"
          }
        >
          {edge ? (
            <>
              <Status value={edge.approval} />
              <KeyValue
                items={{
                  Type: edge.type,
                  Direction: `${objects.find((o) => o.id === edge.source)?.name} → ${objects.find((o) => o.id === edge.target)?.name}`,
                  Scope: edge.scope,
                  Cardinality: edge.cardinality,
                  Provenance: edge.provenance,
                  "Field mapping": edge.sourceField
                    ? `${edge.sourceField} → ${edge.targetField}`
                    : undefined,
                }}
              />
              {state.relationships.some((r) => r.id === edge.id) && (
                <Button
                  onClick={() => {
                    setEdgeLabel(edge.label);
                    setEdgeScope(edge.scope);
                    setCard(edge.cardinality);
                    setAttempted(false);
                    setEditing(true);
                  }}
                >
                  Edit relationship
                </Button>
              )}
            </>
          ) : obj ? (
            <>
              <h3>{obj.name}</h3>
              <p>{obj.type}</p>
              {ks.some((k) => k.id === obj.id) && (
                <Button onClick={() => onObject(obj.id)}>
                  Open definition
                </Button>
              )}
              {!list && (
                <Button
                  onClick={() =>
                    flow.fitView({
                      nodes: [{ id: obj.id }],
                      duration: 300,
                      maxZoom: 1.2,
                    })
                  }
                >
                  Focus node
                </Button>
              )}
            </>
          ) : (
            <p className="muted">
              Select a node or edge. Use the list alternative for keyboard
              navigation.
            </p>
          )}
          <Callout>
            A declared edge is not proof of an executable or correct join.
            Missing lineage coverage is unknown.
          </Callout>
          {assetId && (
            <p className="muted">
              Known impact includes only visible fixture relationships. Hidden
              endpoints are omitted; no counts or labels disclose them.
            </p>
          )}
        </Panel>
      </div>
      {editing && edge && (
        <Modal
          title="Edit relationship declaration"
          description="This creates a draft declaration; it does not prove the join."
          onClose={closeEditor}
        >
          <fieldset
            disabled={saving}
            style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
          >
            <p className="cg-draft-status" role="status">
              {dirty ? "Unsaved relationship changes" : "No unsaved changes"}
            </p>
            {attempted && errors.length > 0 && (
              <div className="cg-error" role="alert">
                <strong>Check the relationship details</strong>
                <ul>
                  {errors.map((error) => (
                    <li key={String(error)}>{error}</li>
                  ))}
                </ul>
              </div>
            )}
            <TextInput
              label="Relationship label"
              value={edgeLabel}
              onChange={setEdgeLabel}
            />
            <TextInput
              label="Relationship scope"
              value={edgeScope}
              onChange={setEdgeScope}
            />
            <TextInput
              label="Declared cardinality"
              value={card}
              onChange={setCard}
            />
            <div className="cg-form-actions">
              <Button onClick={closeEditor}>Cancel</Button>
              <Button
                variant="primary"
                onClick={async () => {
                  setAttempted(true);
                  if (errors.length || saving) return;
                  setSaving(true);
                  const ok = await command<Relationship>(
                    "relationship.save",
                    {
                      relationship: {
                        ...edge,
                        label: edgeLabel.trim(),
                        scope: edgeScope.trim(),
                        cardinality: card.trim(),
                      },
                    },
                    "Draft relationship saved.",
                  );
                  setSaving(false);
                  if (ok) {
                    guard.markClean();
                    setEdge(ok);
                    setEditing(false);
                  }
                }}
              >
                {saving ? "Saving…" : "Save draft relationship"}
              </Button>
            </div>
          </fieldset>
        </Modal>
      )}
    </div>
  );
}
