/** Transport only. Context resolution, provider policy and persistence live in Python. */
export interface AuthoredRecord {
  id: string;
  kind:
    "domain" | "knowledge" | "mapping" | "configuration" | "review" | "design";
  title: string;
  content: string;
  references: string[];
  evidence: { origin: string; revision: string }[];
  approval?: "draft" | "reviewed";
}
export interface WorkspaceDocument {
  schema_version: 1;
  records: AuthoredRecord[];
}
export interface WorkspaceSnapshot {
  revision: number;
  document: WorkspaceDocument;
  history?: { revision: number; reason: string }[];
}
export interface LocalContext {
  context_id: string;
  project_name: string;
  source: Record<string, unknown>;
  capabilities: Record<string, boolean>;
}
export async function localRequest<T = any>(
  path: string,
  body: unknown = {},
): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(35000),
  });
  if (!response.headers.get("content-type")?.includes("application/json"))
    throw Error(
      "Local backend is not configured. Start with the documented local service configuration.",
    );
  const value = await response.json();
  if (!response.ok)
    throw Error(
      value.error || "Local request failed; no demo fallback was used.",
    );
  return value;
}
export const callCore = (name: string, args: Record<string, unknown> = {}) =>
  localRequest("tool", { name, arguments: args });
