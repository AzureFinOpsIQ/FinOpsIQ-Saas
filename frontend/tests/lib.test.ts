import { afterEach, describe, expect, it, vi } from "vitest";
import { api, loginUrl, logoutUrl } from "@/lib/api";
import { cn, money } from "@/lib/utils";

describe("frontend utilities", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("merges tailwind class names predictably", () => {
    expect(cn("rounded", "px-2", false && "hidden", "px-4")).toContain("rounded");
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("formats money with fallback currency", () => {
    expect(money(1234.5, "USD")).toContain("1,234.5");
    expect(money(12, "")).toContain("12");
  });

  it("builds auth endpoint URLs from the configured API base", () => {
    expect(loginUrl).toBe("/api/auth/login");
    expect(logoutUrl).toBe("/api/auth/logout");
  });

  it("adds tenant and subscription headers to API requests", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    } as Response);

    const result = await api<{ ok: boolean }>(
      "/api/resources",
      { tenantId: "tenant-1", subscriptionId: "sub-1" },
      { method: "POST", body: JSON.stringify({ page: 1 }) },
    );

    expect(result).toEqual({ ok: true });
    const [, init] = fetchMock.mock.calls[0];
    const headers = init?.headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-Tenant-ID")).toBe("tenant-1");
    expect(headers.get("X-Subscription-ID")).toBe("sub-1");
    expect(init?.credentials).toBe("include");
    expect(init?.cache).toBe("no-store");
  });

  it("throws response details for non-auth API errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => "upstream failed",
    } as Response);

    await expect(api("/api/costs/summary")).rejects.toThrow("upstream failed");
  });
});
