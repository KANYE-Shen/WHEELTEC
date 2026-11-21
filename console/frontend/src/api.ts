export async function api<T = unknown>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch("/api/v1/" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    let d;
    try {
      d = await response.json();
    } catch {}
    const detail: unknown = d?.detail;
    const message = typeof detail === "string" ? detail :
      detail && typeof detail === "object" && "message" in detail &&
        typeof detail.message === "string" ? detail.message : `请求失败 ${response.status}`;
    throw new Error(message);
  }
  return response.json();
}
export function socket(path: string) {
  return new WebSocket(`ws://${location.host}/api/v1/${path}`);
}
