import { useDraftGuard } from "./draftGuard";
import React, { useState } from "react";
import { Check, Download, ArrowRight } from "@phosphor-icons/react";
import { useRepo } from "./store";
import { knowledgeView, assetView } from "./services";
import type { Proposal } from "./contracts";
import {
  Panel,
  Title,
  Button,
  Status,
  KeyValue,
  Json,
  Callout,
  TextInput,
  Select,
  Modal,
  downloadJSON,
  StateNotice,
} from "./components";
export function ChangeDiff({
  before,
  after,
}: {
  before: unknown;
  after: unknown;
}) {
  return (
    <div className="diff-grid">
      <div>
        <div className="diff-label">CURRENT / BEFORE</div>
        {typeof before === "string" ? (
          <p className="diff-text">{before}</p>
        ) : (
          <Json value={before} />
        )}
      </div>
      <div>
        <div className="diff-label added">PROPOSED / AFTER</div>
        {typeof after === "string" ? (
          <p className="diff-text">{after}</p>
        ) : (
          <Json value={after} />
        )}
      </div>
    </div>
  );
}
export function Changes({ targetId }: { targetId?: string }) {
  const { state, reader, command, simulation } = useRepo();
  const [selected, setSelected] = useState<string[]>([]),
    [focus, setFocus] = useState<string | null>(null),
    [observeId, setObserveId] = useState(targetId || "");
  const allowedKnowledge = new Set(
      knowledgeView(state, reader).map((k) => k.id),
    ),
    allowedAssets = new Set(assetView(state, reader).map((a) => a.id));
  const proposals = state.proposals.filter(
    (p) =>
      allowedKnowledge.has(p.originId) &&
      (!state.assets.some((a) => a.id === p.targetId) ||
        allowedAssets.has(p.targetId)) &&
      (!targetId || p.targetId === targetId),
  );
  const focusedId = focus || proposals.at(-1)?.id;
  const p = proposals.find((p) => p.id === focusedId);
  const eligible = selected.filter((id) =>
    proposals.some(
      (p) => p.id === id && ["Reviewed", "Failed"].includes(p.state),
    ),
  );
  return (
    <div className={targetId ? "" : "screen-pad"}>
      {!targetId && (
        <Title
          eyebrow="Changes / Native review & reconciliation"
          title="Review changes"
          description="Proposals come from your session edits. Review and delivery are separate steps."
        />
      )}
      {!simulation && (
        <Panel title="Observe native metadata">
          <p className="muted">
            Read the exact configured destination before editing. Observation
            and readback never write to the destination.
          </p>
          <Select
            label="Native target"
            value={observeId}
            onChange={setObserveId}
            options={[
              { value: "", label: "Choose a target" },
              ...state.targets
                .filter(
                  (t) =>
                    ["genie", "table", "view", "unity_catalog"].includes(
                      t.kind,
                    ) &&
                    (!targetId || t.id === targetId),
                )
                .map((t) => ({ value: t.id, label: t.name })),
            ]}
          />
          <Button
            disabled={!observeId || reader !== "steward"}
            onClick={async () => {
              await command(
                "target.refresh",
                { id: observeId },
                "Native snapshot refreshed. Reopen your editor to use this complete snapshot.",
              );
            }}
          >
            Read current native metadata
          </Button>
        </Panel>
      )}
      <div className="toolbar">
        <span>
          {
            proposals.filter((p) => !["Verified", "Exported"].includes(p.state))
              .length
          }{" "}
          pending changes
        </span>
        <Button
          variant="primary"
          disabled={!eligible.length}
          onClick={async () =>
            await command(
              "proposal.deliver",
              { ids: eligible },
              "Selected reviewed items processed. Inspect receipts below.",
            )
          }
        >
          {simulation
            ? "Simulate selected delivery"
            : "Process reviewed proposals"}{" "}
          ({eligible.length})
        </Button>
      </div>
      {!proposals.length && (
        <StateNotice title="No proposed changes yet">
          Edit a description, metric view, Page or Genie configuration under
          Sources to prepare an exact proposal.
        </StateNotice>
      )}
      <div className="change-layout">
        <div>
          {proposals.map((p) => (
            <div
              className={`change-card ${focusedId === p.id ? "chosen" : ""}`}
              key={p.id}
            >
              <label className="check">
                <input
                  type="checkbox"
                  aria-label={`Select ${p.id}`}
                  checked={selected.includes(p.id)}
                  disabled={["Verified", "Exported"].includes(p.state)}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, p.id]
                        : selected.filter((id) => id !== p.id),
                    )
                  }
                />
                <strong>
                  {state.targets.find((t) => t.id === p.targetId)?.name}
                </strong>
              </label>
              <div className="mini-row">
                <span>
                  {p.field} · {p.id}
                </span>
                <Status value={p.state} />
              </div>
              <Button onClick={() => setFocus(p.id)}>
                Review exact change
              </Button>
            </div>
          ))}
        </div>
        <div>
          {p ? (
            <ProposalReview proposal={p} />
          ) : (
            proposals.length > 0 && (
              <StateNotice title="Choose a proposal">
                Inspect the exact values, destination audience and pinned
                revision before approval.
              </StateNotice>
            )
          )}
        </div>
      </div>
      <Panel title="Delivery ledger">
        {state.deliveries
          .filter((d) => proposals.some((p) => p.id === d.proposalId))
          .map((d) => (
            <div className="receipt" key={d.id}>
              <div className="inline">
                <strong>{d.proposalId}</strong>
                <Status value={d.state} />
              </div>
              <p>{d.message}</p>
              <KeyValue
                items={{
                  "Save acknowledged": d.acknowledged
                    ? "Yes"
                    : simulation
                      ? "No"
                      : "Unknown",
                  "Read-back": d.readback,
                  "Ontology indexing": d.indexing,
                  "Observed answer use": d.answerUse,
                }}
              />
            </div>
          ))}
        {!state.deliveries.length && (
          <p className="muted">
            No delivery attempts. Saving does not imply ontology indexing or
            answer use.
          </p>
        )}
      </Panel>
    </div>
  );
}
function ProposalReview({ proposal: p }: { proposal: Proposal }) {
  const { state, command, reader, simulation } = useRepo();
  const t = state.targets.find((t) => t.id === p.targetId)!;
  return (
    <Panel title="Exact target change">
      <p className="review-target">
        <strong>{t.name}</strong> · {p.field}
      </p>
      <p className="muted">{p.reason}</p>
      <p className="review-audience">
        Audience: {p.audience} · UOL revision {p.originRevision}
      </p>
      <ChangeDiff before={p.before} after={p.after} />
      <details className="review-evidence">
        <summary>Evidence, pinned revisions & audience</summary>
        <KeyValue
          items={{
            Target: `${t.providerId} / ${t.id}`,
            Field: p.field,
            "Pinned UOL revision": `${p.originId} @ ${p.originRevision}`,
            "Observed target revision": p.expectedRevision,
            "Current target revision": t.revision,
            Audience: p.audience,
            Reason: p.reason,
            Evidence: p.evidence,
            Dependencies: p.dependencies.join(", ") || "None",
            "Review decision": p.reviewDecision || "Not reviewed",
            "Pinned native fingerprint":
              p.nativeBaseFingerprint || "Not observed",
          }}
        />
      </details>
      {JSON.stringify(t.content[p.field] ?? null) !==
        JSON.stringify(p.before) && (
        <Panel title="Current target now differs">
          <Json value={t.content[p.field]} />
        </Panel>
      )}
      <Callout tone={t.atomic ? "teal" : "amber"}>
        {!simulation
          ? "Native writes are unsupported. Review this exact proposal and export a handoff for the native destination."
          : t.atomic
            ? "Mock ETag precondition enforced."
            : "No atomic native conditional update is assumed. The synchronous mock checks a revision; a real adapter needs an explicit race strategy."}
      </Callout>
      {!simulation && (
        <Panel title="Native observation and verification">
          <div className="inline">
            <Button
              disabled={reader !== "steward"}
              onClick={async () => {
                await command(
                  "target.refresh",
                  { id: p.targetId },
                  "Current native metadata observed; proposal revision remains pinned.",
                );
              }}
            >
              Refresh native snapshot
            </Button>
            <Button
              disabled={reader !== "steward" || !p.nativeBaseFingerprint}
              onClick={async () => {
                await command(
                  "proposal.check",
                  { id: p.id },
                  "Native preflight completed. Inspect the result below.",
                );
              }}
            >
              Check native preflight
            </Button>
            <Button
              disabled={reader !== "steward" || !p.nativeBaseFingerprint}
              onClick={async () => {
                await command(
                  "proposal.reconcile",
                  { id: p.id },
                  "Fresh native readback completed. No save acknowledgement is inferred.",
                );
              }}
            >
              Read back native values
            </Button>
          </div>
          <p className="muted">
            Permissions and audience must be independently verified. A matching
            readback confirms observed values only; save acknowledgement,
            indexing and answer use remain unknown.
          </p>
          {p.nativeResult && (
            <>
              <Status value={String(p.nativeResult.status)} />
              <Json value={p.nativeResult} />
            </>
          )}
        </Panel>
      )}
      <div className="inline">
        <Button
          variant="primary"
          disabled={
            reader !== "steward" || !["Draft", "Conflict"].includes(p.state)
          }
          onClick={async () =>
            await command(
              "proposal.review",
              { id: p.id },
              "Proposal reviewed; delivery still pending.",
            )
          }
        >
          Approve proposal
        </Button>
        {p.state === "Conflict" && (
          <Button
            onClick={async () =>
              await command(
                "proposal.rebase",
                { id: p.id },
                "Rebased to current target. Review again.",
              )
            }
          >
            Reconcile current target
          </Button>
        )}
        {["Unsupported", "Reviewed"].includes(p.state) &&
          (!simulation || t.capability === "unsupported") && (
            <Button
              icon={Download}
              onClick={async () => {
                const handoff = await command("proposal.export", { id: p.id });
                if (handoff) downloadJSON(handoff, "uol-reviewed-handoff.json");
              }}
            >
              Export reviewed handoff
            </Button>
          )}
      </div>
      {simulation && (
        <details className="simulation-controls">
          <summary>Demo scenarios</summary>
          <div className="inline">
            {" "}
            <Button
              disabled={["Verified", "Exported"].includes(p.state)}
              onClick={async () =>
                await command("target.simulate", {
                  id: p.targetId,
                  scenario: "drift",
                })
              }
            >
              Simulate target drift
            </Button>
            <Button
              onClick={async () =>
                await command("target.simulate", {
                  id: p.targetId,
                  scenario: "failure",
                })
              }
            >
              Fail next write
            </Button>
            <Button
              onClick={async () =>
                await command("target.simulate", {
                  id: p.targetId,
                  scenario: "mismatch",
                })
              }
            >
              Diverge read-back
            </Button>
          </div>
        </details>
      )}
    </Panel>
  );
}
export function ProposalDialog({
  targetId,
  field,
  initial,
  onClose,
  onSaved,
}: {
  targetId: string;
  field: string;
  initial: unknown;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const { state, reader, command } = useRepo();
  const a = state.assets.find((a) => a.id === targetId);
  const [origin, setOrigin] = useState(
      a?.knowledgeIds.find((id) =>
        knowledgeView(state, reader).some((k) => k.id === id),
      ) ||
        knowledgeView(state, reader)[0]?.id ||
        "",
    ),
    [text, setText] = useState(
      typeof initial === "string" ? initial : JSON.stringify(initial, null, 2),
    ),
    [reason, setReason] = useState(
      "Align native metadata with reviewed UOL meaning.",
    );
  const [error, setError] = useState("");
  const guard = useDraftGuard(
    text !==
      (typeof initial === "string"
        ? initial
        : JSON.stringify(initial, null, 2)) ||
      reason !== "Align native metadata with reviewed UOL meaning.",
    "Native metadata proposal",
  );
  const t = state.targets.find((t) => t.id === targetId)!;
  return (
    <Modal
      wide
      title={`Propose ${field} change`}
      description="This saves a UOL proposal. It does not change the native target."
      onClose={() => guard.attempt(onClose)}
    >
      <Select
        label="UOL origin"
        value={origin}
        onChange={setOrigin}
        options={knowledgeView(state, reader).map((k) => ({
          value: k.id,
          label: `${k.name} · revision ${k.version}`,
        }))}
      />
      <TextInput
        label={`Proposed ${field}${field === "tags" ? " (JSON object)" : ""}`}
        value={text}
        onChange={setText}
        area
      />
      <TextInput label="Reason" value={reason} onChange={setReason} />
      <Panel title="Current native value">
        <Json value={t.content[field] ?? null} />
      </Panel>
      {error && <StateNotice title={error} kind="error" />}
      <Button
        variant="primary"
        onClick={async () => {
          setError("");
          let after: unknown;
          try {
            after = field === "tags" ? JSON.parse(text) : text;
            if (
              field === "tags" &&
              (!after ||
                Array.isArray(after) ||
                typeof after !== "object" ||
                Object.values(after).some((v) => typeof v !== "string"))
            )
              throw Error("Tags must be an object of string values");
          } catch (error) {
            setError(
              error instanceof Error ? error.message : "Invalid proposal value",
            );
            return;
          }
          const p = await command(
            "proposal.create",
            { proposal: { originId: origin, targetId, field, after, reason } },
            "Draft proposal saved. Ready for review.",
          );
          if (p) {
            guard.markClean();
            if (onSaved) onSaved();
            else onClose();
          }
        }}
      >
        Save draft proposal
      </Button>
    </Modal>
  );
}
