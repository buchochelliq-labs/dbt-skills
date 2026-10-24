import React, { useState, useEffect } from "react";
import {
  Graph,
  Sparkle,
  MagnifyingGlass,
  List,
  ArrowRight,
  Download,
  ArrowCounterClockwise,
  ShieldCheck,
  FolderSimple,
  X,
} from "@phosphor-icons/react";
import { Repository, useRepo } from "./store";
import { knowledgeView, assetView, path } from "./services";
import { Domains } from "./DomainScreens";
import { Sources } from "./SourceScreens";
import { Connections, AgentPreview } from "./ContextConnections";
import { GraphScreen } from "./GraphScreen";
import { Changes } from "./ChangesScreen";
import {
  Button,
  Modal,
  TypeIcon,
  downloadJSON,
  StateNotice,
  TextInput,
  Json,
} from "./components";
import "./workspace.css";
import { DraftGuardProvider, useNavigationGuard } from "./draftGuard";
const nav = ["Domains", "Knowledge graph", "Sources", "Connections", "Changes"];
export function App() {
  return (
    <DraftGuardProvider>
      <Repository>
        <Workspace />
      </Repository>
    </DraftGuardProvider>
  );
}
function Workspace() {
  const attempt = useNavigationGuard();
  const {
    state,
    reader,
    setReader,
    reset,
    notice,
    setNotice,
    command,
    simulation,
    revision,
  } = useRepo();
  const [page, setPage] = useState("Domains"),
    [domain, setDomain] = useState("customer"),
    [object, setObject] = useState<string | null>(null),
    [mobile, setMobile] = useState(false),
    [modal, setModal] = useState<
      "context" | "search" | "reset" | "transfer" | null
    >(null),
    [context, setContext] = useState<string | undefined>(),
    [q, setQ] = useState(""),
    [requestedAsset, setRequestedAsset] = useState<{
      id: string;
      sequence: number;
    }>(),
    [closed, setClosed] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [importText, setImportText] = useState(""),
    [importPreview, setImportPreview] = useState<any>(null);
  const activeDomain =
    state.domains.find((d) => d.id === domain)?.id || state.domains[0]?.id;
  async function exportWorkspace() {
    setBusy(true);
    try {
      const envelope = await command("workspace.export", {});
      if (envelope !== undefined) downloadJSON(envelope, "uol-workspace.json");
    } finally {
      setBusy(false);
    }
  }
  function go(p: string) {
    attempt(() => {
      setPage(p);
      setMobile(false);
      window.scrollTo(0, 0);
    });
  }
  function openObject(id: string) {
    const k = knowledgeView(state, reader).find((k) => k.id === id);
    if (k)
      attempt(() => {
        setDomain(k.domain);
        setObject(id);
        go("Domains");
        setModal(null);
      });
  }
  function preview(id?: string) {
    setContext(id);
    setModal("context");
  }
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setModal("search");
      }
      if (e.key === "Escape") setMobile(false);
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
  useEffect(() => {
    if (notice) {
      const t = setTimeout(() => setNotice(""), 7000);
      return () => clearTimeout(t);
    }
  }, [notice]);
  function tree(id: string, depth = 0): React.ReactNode {
    const d = state.domains.find((d) => d.id === id);
    if (!d) return null;
    const children = state.domains.filter((d) => d.parent === id);
    const open = !closed.includes(id);
    return (
      <div key={id}>
        <div
          className={`domain-tree-row ${domain === id ? "selected" : ""}`}
          style={{ paddingLeft: 10 + depth * 13 }}
        >
          {children.length ? (
            <button
              aria-label={`${open ? "Collapse" : "Expand"} ${d.name}`}
              className="tree-toggle"
              onClick={() =>
                setClosed(
                  open ? [...closed, id] : closed.filter((x) => x !== id),
                )
              }
            >
              {open ? "−" : "+"}
            </button>
          ) : (
            <span className="tree-spacer" />
          )}
          <button
            className="tree-label"
            onClick={() =>
              attempt(() => {
                setDomain(id);
                setObject(null);
                go("Domains");
              })
            }
          >
            <FolderSimple size={16} />
            <span>{d.name}</span>
          </button>
        </div>
        {open && children.map((d) => tree(d.id, depth + 1))}
      </div>
    );
  }
  return (
    <div
      className={`app-shell uol-v2 ${["Domains", "Knowledge graph"].includes(page) ? "" : "contextual-workspace"}`}
    >
      <a href="#main" className="skip-link">
        Skip to workspace
      </a>
      <header className="app-header">
        <div className="brand-group">
          <button
            className="mobile-menu icon-button"
            aria-label="Open workspace navigation"
            onClick={() => setMobile(!mobile)}
          >
            <List size={23} />
          </button>
          <button className="brand" onClick={() => go("Domains")}>
            <Graph size={31} />
            <strong>UOL</strong>
          </button>
          <span className="brand-caption">Unified Ontology Layer</span>
        </div>
        <nav className="top-nav" aria-label="Primary navigation">
          {nav.map((p) => (
            <button
              key={p}
              className={page === p ? "active" : ""}
              aria-current={page === p ? "page" : undefined}
              onClick={() => go(p)}
            >
              {p}
              {p === "Changes" && state.proposals.length > 0 && (
                <span className="nav-count">
                  {
                    state.proposals.filter(
                      (p) => !["Verified", "Exported"].includes(p.state),
                    ).length
                  }
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="header-actions">
          <button
            className="icon-button"
            aria-label="Search workspace"
            onClick={() => setModal("search")}
          >
            <MagnifyingGlass size={21} />
          </button>
          <Button icon={Sparkle} onClick={() => preview()}>
            Agent context
          </Button>
          <span className="demo-pill">
            {simulation ? "Simulation" : "Local backend"}
          </span>
        </div>
      </header>
      <div className="app-content">
        {mobile && (
          <button
            className="sidebar-overlay"
            aria-label="Close navigation"
            onClick={() => setMobile(false)}
          />
        )}
        <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
          <div className="workspace-picker">
            <span className="workspace-icon">
              <Graph size={22} />
            </span>
            <span>
              <strong>
                {simulation ? "Sample enterprise" : "Project workspace"}
              </strong>
              <small>Knowledge workspace</small>
            </span>
          </div>
          {["Domains", "Knowledge graph"].includes(page) && (
            <>
              <div className="sidebar-heading">BUSINESS DOMAINS</div>
              <nav aria-label="Domain hierarchy">
                {state.domains.filter((d) => !d.parent).map((d) => tree(d.id))}
              </nav>
            </>
          )}
          <div className="sidebar-divider" />
          <Button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await command("catalog.sync", {}, "Catalog synchronized.");
              } finally {
                setBusy(false);
              }
            }}
          >
            Sync catalog
          </Button>
          <Button onClick={() => setModal("transfer")}>
            Import / export workspace
          </Button>
          <div className="sidebar-heading">SESSION CONTEXT</div>
          <label className="field reader-select">
            <span className="field-label">
              {simulation ? "Simulated reader" : "Reader"}
            </span>
            <select
              value={reader}
              onChange={(e) => {
                const value = e.target.value;
                attempt(() => {
                  setReader(value as any);
                  setObject(null);
                  setModal(null);
                });
              }}
            >
              <option value="steward">Metadata steward</option>
              <option value="restricted">Restricted reader</option>
            </select>
          </label>
          <p className="sidebar-note">
            Business ownership is independent of native permissions.
          </p>
          <div className="sidebar-bottom">
            <div>
              <ShieldCheck size={22} />
              <span>
                <strong>Metadata only</strong>
                <small>Meaning, never the records.</small>
              </span>
            </div>
            <button disabled={busy} onClick={exportWorkspace}>
              <Download size={16} />
              Export visible workspace
            </button>
            {simulation && (
              <button onClick={() => setModal("reset")}>
                <ArrowCounterClockwise size={16} />
                Reset demo
              </button>
            )}
          </div>
        </aside>
        <main id="main" className="page-container">
          {page === "Domains" && activeDomain && (
            <Domains
              domainId={activeDomain}
              selected={object}
              onDomain={(id) =>
                attempt(() => {
                  setDomain(id);
                  setObject(null);
                })
              }
              onObject={(id) => (id ? openObject(id) : setObject(null))}
              onContext={preview}
            />
          )}{" "}
          {page === "Domains" && !activeDomain && (
            <StateNotice title="No domains in this workspace">
              Import a workspace to begin organizing knowledge.
            </StateNotice>
          )}
          {page === "Knowledge graph" && <GraphScreen onObject={openObject} />}{" "}
          <div hidden={page !== "Sources"}>
            <Sources
              requestedAsset={requestedAsset}
              onObject={openObject}
              onContext={preview}
            />
          </div>{" "}
          {page === "Connections" && <Connections />}{" "}
          {page === "Changes" && <Changes />}
        </main>
      </div>
      <footer className="app-footer">
        <span>
          <i className="footer-dot" />
          {simulation
            ? "Session-only simulation · no live integrations"
            : `Local backend · revision ${revision}`}
        </span>
        <span>Provider-neutral knowledge · UOL companion</span>
      </footer>
      {notice && (
        <div
          className="toast"
          role={notice.startsWith("Error") ? "alert" : "status"}
        >
          <span>{notice}</span>
          <button
            aria-label="Dismiss notification"
            className="icon-button"
            onClick={() => setNotice("")}
          >
            <X />
          </button>
        </div>
      )}
      {modal === "context" && (
        <Modal
          wide
          title="Agent context preview"
          description="See precisely which facts an agent can use, and why."
          onClose={() => setModal(null)}
        >
          <AgentPreview key={context || "global"} objectId={context} />
        </Modal>
      )}
      {modal === "search" && (
        <Modal
          wide
          title="Search permitted metadata"
          onClose={() => setModal(null)}
        >
          <input
            autoFocus
            aria-label="Search all visible knowledge"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search knowledge or source metadata…"
          />
          {knowledgeView(state, reader)
            .filter((k) =>
              `${k.name} ${k.synonyms.join(" ")}`
                .toLowerCase()
                .includes(q.toLowerCase()),
            )
            .map((k) => (
              <button
                className="object-row"
                key={k.id}
                onClick={() => openObject(k.id)}
              >
                <TypeIcon type={k.type} />
                <span>
                  <strong>{k.name}</strong>
                  <small>
                    {k.scope} ·{" "}
                    {path(state, k.domain)
                      .map((d) => d.name)
                      .join(" / ")}
                  </small>
                </span>
                <ArrowRight size={16} />
              </button>
            ))}
          {assetView(state, reader)
            .filter((a) => q && a.name.toLowerCase().includes(q.toLowerCase()))
            .map((a) => (
              <button
                className="object-row"
                key={a.id}
                onClick={() => {
                  setRequestedAsset((previous) => ({
                    id: a.id,
                    sequence: (previous?.sequence || 0) + 1,
                  }));
                  setModal(null);
                  go("Sources");
                }}
              >
                <TypeIcon type={a.type} />
                <span>
                  <strong>{a.name}</strong>
                  <small>
                    {state.providers.find((p) => p.id === a.providerId)?.name} ·{" "}
                    {a.type.replace("_", " ")}
                  </small>
                </span>
                <ArrowRight size={16} />
              </button>
            ))}
        </Modal>
      )}
      {modal === "transfer" && (
        <Modal
          wide
          title="Import / export workspace"
          onClose={() => {
            if (!busy) setModal(null);
          }}
        >
          <Button disabled={busy} icon={Download} onClick={exportWorkspace}>
            Export visible workspace
          </Button>
          <fieldset disabled={busy} style={{ border: 0, padding: 0 }}>
            <TextInput
              label="Workspace import JSON"
              value={importText}
              area
              onChange={(value) => {
                setImportText(value);
                setImportPreview(null);
              }}
            />
            <Button
              disabled={busy || !importText.trim()}
              onClick={async () => {
                setBusy(true);
                setImportPreview(null);
                try {
                  const envelope = JSON.parse(importText);
                  const result = await command("workspace.import.preview", {
                    envelope,
                  });
                  if (result !== undefined) setImportPreview(result);
                } catch (error) {
                  setNotice(`Error: ${(error as Error).message}`);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Validate and preview import
            </Button>
          </fieldset>
          {importPreview && (
            <>
              <h3>Review import changes</h3>
              <Json value={importPreview} />
              <Button
                variant="primary"
                disabled={
                  busy || !(importPreview.previewId || importPreview.preview_id)
                }
                onClick={() =>
                  attempt(async () => {
                    setBusy(true);
                    try {
                      const result = await command(
                        "workspace.import.apply",
                        {
                          previewId:
                            importPreview.previewId || importPreview.preview_id,
                        },
                        "Workspace imported.",
                      );
                      if (result !== undefined) {
                        setImportText("");
                        setImportPreview(null);
                        setObject(null);
                        setModal(null);
                      }
                    } finally {
                      setBusy(false);
                    }
                  })
                }
              >
                Apply reviewed import
              </Button>
            </>
          )}
        </Modal>
      )}
      {modal === "reset" && simulation && (
        <Modal
          title="Reset this demo session?"
          description="This clears local edits, proposals, deliveries and cache entries. Export anything you want to retain first."
          onClose={() => setModal(null)}
        >
          <Button
            variant="primary"
            onClick={() =>
              attempt(async () => {
                const result = await reset();
                if (result === undefined) return;
                setDomain("customer");
                setObject(null);
                setPage("Domains");
                setModal(null);
              })
            }
          >
            Reset session
          </Button>
        </Modal>
      )}
    </div>
  );
}
