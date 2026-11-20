/** Klien API: semua request /api/v1 memakai token sesi dari <meta name="klipin-token">. */

export const TOKEN =
  document.querySelector<HTMLMetaElement>('meta[name="klipin-token"]')?.content ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields: Record<string, string> = {},
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Klipin-Token", TOKEN);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let resp: Response;
  try {
    resp = await fetch(`/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "NETWORK", "Klipin tidak bisa dihubungi. Pastikan aplikasi masih berjalan.");
  }
  if (resp.ok) return (await resp.json()) as T;
  const body = await resp.json().catch(() => null);
  const err = body?.error;
  throw new ApiError(
    resp.status,
    err?.code ?? "INTERNAL_ERROR",
    err?.message ?? "Terjadi kesalahan di Klipin. Detail ada di log.",
    err?.fields ?? {},
  );
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });
