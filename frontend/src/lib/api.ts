const API = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");

export function apiUrl(path: string, base = API) {
  const normalizedBase = base.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (normalizedBase.endsWith("/api") && normalizedPath.startsWith("/api/")) {
    return `${normalizedBase}${normalizedPath.slice(4)}`;
  }
  return `${normalizedBase}${normalizedPath}`;
}

export type Scope = { tenantId: string; subscriptionId: string };

export async function api<T>(
  path: string,
  scope?: Scope,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (scope?.tenantId) headers.set("X-Tenant-ID", scope.tenantId);
  if (scope?.subscriptionId) {
    headers.set("X-Subscription-ID", scope.subscriptionId);
  }
  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.location.href = apiUrl("/api/auth/logout");
      return new Promise(() => {}) as Promise<T>;
    }
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const loginUrl = apiUrl("/api/auth/login");
export const logoutUrl = apiUrl("/api/auth/logout");
