import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/app-shell";
import { ScopeProvider } from "@/components/scope-provider";
import { Providers } from "@/components/providers";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: vi.fn(),
    logoutUrl: "/api/auth/logout",
  };
});

const apiMock = vi.mocked(api);

describe("application shell and scope provider", () => {
  beforeEach(() => {
    apiMock.mockReset();
    localStorage.clear();
    (globalThis as { __mockPathname?: string }).__mockPathname = "/dashboard";
  });

  it("loads scope data and displays the authenticated user from /api/auth/me", async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path === "/api/tenants") {
        return [{ tenantId: "tenant-1", displayName: "Tenant One" }];
      }
      if (path === "/api/subscriptions") {
        return [
          {
            tenantId: "tenant-1",
            subscriptionId: "sub-1",
            displayName: "Production Subscription",
          },
        ];
      }
      if (path === "/api/auth/me") {
        return {
          tenant_id: "tenant-1",
          user_id: "user-2",
          email: "user-2@example.com",
          display_name: "User Two",
          roles: ["tenant_admin"],
        };
      }
      return {};
    });

    render(
      <ScopeProvider>
        <AppShell>
          <div>Dashboard content</div>
        </AppShell>
      </ScopeProvider>,
    );

    expect(await screen.findByText("User Two")).toBeInTheDocument();
    expect(screen.getByText("user-2@example.com · tenant admin")).toBeInTheDocument();
    expect(screen.getByLabelText("Tenant")).toHaveValue("tenant-1");
    expect(await screen.findByLabelText("Subscription")).toHaveValue("sub-1");
    expect(screen.getByText("Dashboard content")).toBeInTheDocument();
  });

  it("clears stale user-scoped selections when a different user signs in", async () => {
    localStorage.setItem("currentUserId", "user-1");
    localStorage.setItem("tenantId", "tenant-old");
    localStorage.setItem("subscriptionId", "sub-old");

    apiMock.mockImplementation(async (path: string) => {
      if (path === "/api/tenants") {
        return [{ tenantId: "tenant-1", displayName: "Tenant One" }];
      }
      if (path === "/api/subscriptions") {
        return [{ tenantId: "tenant-1", subscriptionId: "sub-1", displayName: "Sub One" }];
      }
      if (path === "/api/auth/me") {
        return {
          tenant_id: "tenant-1",
          user_id: "user-2",
          email: "user-2@example.com",
          display_name: "User Two",
          roles: ["tenant_user"],
        };
      }
      return {};
    });

    render(
      <ScopeProvider>
        <AppShell>
          <div>Dashboard content</div>
        </AppShell>
      </ScopeProvider>,
    );

    await screen.findByText("User Two");

    expect(localStorage.getItem("currentUserId")).toBe("user-2");
    expect(localStorage.getItem("tenantId")).toBeNull();
    expect(localStorage.getItem("subscriptionId")).toBeNull();
  });

  it("updates selected scope and routes logout through the configured endpoint", async () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "" },
    });

    apiMock.mockImplementation(async (path: string) => {
      if (path === "/api/tenants") {
        return [
          { tenantId: "tenant-1", displayName: "Tenant One" },
          { tenantId: "tenant-2", displayName: "Tenant Two" },
        ];
      }
      if (path === "/api/subscriptions") {
        return [
          { tenantId: "tenant-1", subscriptionId: "sub-1", displayName: "Sub One" },
          { tenantId: "tenant-1", subscriptionId: "sub-2", displayName: "Sub Two" },
        ];
      }
      if (path === "/api/auth/me") {
        return {
          tenant_id: "tenant-1",
          user_id: "user-1",
          email: "user-1@example.com",
          display_name: "User One",
          roles: ["tenant_admin"],
        };
      }
      return {};
    });

    render(
      <ScopeProvider>
        <AppShell>
          <div>Dashboard content</div>
        </AppShell>
      </ScopeProvider>,
    );

    await screen.findByText("User One");
    await screen.findByLabelText("Subscription");
    fireEvent.change(screen.getByLabelText("Tenant"), { target: { value: "tenant-2" } });
    fireEvent.change(screen.getByLabelText("Subscription"), { target: { value: "sub-2" } });
    fireEvent.click(screen.getByLabelText("Sign out"));

    expect(localStorage.getItem("tenantId")).toBe("tenant-2");
    expect(localStorage.getItem("subscriptionId")).toBe("sub-2");
    expect(window.location.href).toBe("/api/auth/logout");
  });

  it("bypasses the shell on public routes and composes providers", async () => {
    (globalThis as { __mockPathname?: string }).__mockPathname = "/";
    apiMock.mockResolvedValue([]);

    render(
      <Providers>
        <AppShell>
          <div>Public content</div>
        </AppShell>
      </Providers>,
    );

    expect(screen.getByText("Public content")).toBeInTheDocument();
    await waitFor(() => {
      expect(apiMock).not.toHaveBeenCalledWith("/api/auth/me");
    });
  });
});
