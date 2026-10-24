/** Transport only. Context resolution, provider policy and persistence live in Python. */
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
