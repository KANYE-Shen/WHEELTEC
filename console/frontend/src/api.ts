export async function api<T = unknown>(
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api/v1/" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let d;
    try {
      d = await response.json();
    } catch {}
    throw new Error(d?.detail || `请求失败 ${response.status}`);
  }
  return response.json();
}
export function socket(path: string) {
  return new WebSocket(`ws://${location.host}/api/v1/${path}`);
}
