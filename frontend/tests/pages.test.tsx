import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Assistant from "@/app/assistant/page";
import Admin from "@/app/admin/page";
import Costs from "@/app/costs/page";
import Dashboard from "@/app/dashboard/page";
import Onboarding from "@/app/onboarding/page";
import Recommendations from "@/app/recommendations/page";
import Resources from "@/app/resources/page";
import { api } from "@/lib/api";

vi.mock("@/components/scope-provider", () => ({
  useScope: () => ({
    scope: { tenantId: "tenant-1", subscriptionId: "sub-1" },
    tenants: [{ tenantId: "tenant-1", displayName: "Tenant One" }],
    subscriptions: [{ tenantId: "tenant-1", subscriptionId: "sub-1", displayName: "Azure Sub" }],
    setTenant: vi.fn(),
    setSubscription: vi.fn(),
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: vi.fn(),
  };
});

const apiMock = vi.mocked(api);

describe("authenticated FinOps pages", () => {
  beforeEach(() => {
    apiMock.mockReset();
  });

  it("renders dashboard metrics from collected cost, resource, and recommendation data", async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path === "/api/costs/summary") {
        return { totals: [{ currency: "INR", amount: 12000 }], recordCount: 8 };
      }
      if (path === "/api/resources") {
        return [
          { resourceName: "appgw-prod", estimatedMonthlyCost: 7000 },
          { resourceName: "vm-prod", estimatedMonthlyCost: 5000 },
        ];
      }
      if (path === "/api/recommendations") {
        return [{ estimatedSavings: 900, currency: "INR" }];
      }
      return {
        status: "ready",
        subscriptions: [
          {
            collection: { status: "completed", recordsCollected: 44 },
            processing: {
              status: "completed",
              completedAt: "2026-06-24T10:00:00Z",
              recordCounts: { costFacts: 8 },
            },
          },
        ],
      };
    });

    render(<Dashboard />);

    expect(await screen.findByText("Total cost")).toBeInTheDocument();
    expect(screen.getByText("8 cost records analyzed")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getAllByText("completed")).toHaveLength(2);
  });

  it("renders resource inventory and can request live inventory views", async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path === "/api/resources") {
        return [
          {
            resourceName: "aks-finops-dev",
            resourceType: "Microsoft.ContainerService/managedClusters",
            resourceGroup: "rg-finops",
            location: "eastus",
            costBasis: "actual",
            sourceSystem: "resourceFacts",
            estimatedMonthlyCost: 699,
            estimatedCostCurrency: "INR",
            wasteLevel: "LOW",
          },
        ];
      }
      return {
        source: "resource-graph",
        timestamp: "2026-06-24T10:00:00Z",
        result_count: 1,
        records: [
          {
            name: "vm-prod",
            type: "Microsoft.Compute/virtualMachines",
            resourceGroup: "rg-finops",
            location: "eastus",
          },
        ],
      };
    });

    render(<Resources />);

    expect(await screen.findByText("aks-finops-dev")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "vms" }));

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith("/api/inventory/vms", {
        tenantId: "tenant-1",
        subscriptionId: "sub-1",
      });
    });
  });

  it("renders actionable recommendations sorted by savings", async () => {
    apiMock.mockResolvedValue([
      {
        title: "idle public ip",
        category: "idle_public_ip",
        content: "Remove unused public IP",
        estimatedSavings: 80,
        currency: "INR",
        sourceSystem: "advisor",
        status: "active",
        resourceId: "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/demo-pip",
      },
    ]);

    render(<Recommendations />);

    expect(await screen.findByText("Unused Public IP Detected")).toBeInTheDocument();
    expect(screen.getByText("Estimated monthly savings")).toBeInTheDocument();
    expect(screen.getByText("demo-pip")).toBeInTheDocument();
    expect(screen.getByText(/Delete the public IP/)).toBeInTheDocument();
  });

  it("submits assistant questions and renders grounded answers", async () => {
    apiMock.mockResolvedValue({
      answer:
        "Executive Summary\nEstimated savings: ₹539/month\nResource aks-finops-dev\nRisk: Low",
    });

    render(<Assistant />);

    fireEvent.click(screen.getByRole("button", { name: "Which resources are idle?" }));

    expect(await screen.findByText(/Executive Summary/)).toBeInTheDocument();
    expect(screen.getByText("₹539/month")).toBeInTheDocument();
    expect(screen.getByText("aks-finops-dev")).toBeInTheDocument();
  });

  it("renders cost analytics from cost, resource, and savings data", async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path.startsWith("/api/costs/trends?granularity=monthly")) {
        return [{ period: "2026-06", currency: "INR", costAmount: 12000 }];
      }
      if (path === "/api/costs/trends") {
        return [
          { date: "2026-06-20", currency: "INR", costAmount: 5000 },
          { date: "2026-06-21", currency: "INR", costAmount: 7000 },
        ];
      }
      if (path === "/api/costs/services") {
        return [
          { service_name: "Virtual Machines", currency: "INR", costAmount: 7000 },
          { service_name: "Virtual Network", currency: "INR", costAmount: 5000 },
        ];
      }
      if (path === "/api/costs/resource-groups") {
        return [{ resource_group: "rg-finops", currency: "INR", costAmount: 12000 }];
      }
      if (path === "/api/resources") {
        return [{ resourceName: "vm-prod", estimatedMonthlyCost: 7000 }];
      }
      return [{ estimatedSavings: 1000, currency: "INR" }];
    });

    render(<Costs />);

    expect(await screen.findByText("Cost Trend")).toBeInTheDocument();
    expect(screen.getByText(/analyzed spend/)).toBeInTheDocument();
    expect(screen.getByText("Cost Breakdown")).toBeInTheDocument();
    expect(screen.getByText("Cost Heat Map")).toBeInTheDocument();
    expect(screen.getByText("rg-finops")).toBeInTheDocument();
  });

  it("renders administration permission and collection health", async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path === "/api/subscriptions") {
        return [
          {
            tenantId: "tenant-1",
            subscriptionId: "sub-1",
            displayName: "Azure Sub",
            onboardingStatus: "completed",
            status: "Enabled",
          },
        ];
      }
      if (path === "/api/tenant-health") {
        return [
          {
            subscriptionId: "sub-1",
            validationStatus: "passed",
            lastChecked: "2026-06-24T10:00:00Z",
            validationResults: {
              subscriptionAccess: { name: "Reader", status: "passed", message: "Reader granted" },
              costManagement: { name: "Cost", status: "passed", message: "Cost access granted" },
              advisor: { name: "Advisor", status: "failed", message: "Advisor missing" },
            },
          },
        ];
      }
      return {
        status: "ready",
        subscriptions: [
          {
            collection: {
              status: "completed",
              completedAt: "2026-06-24T10:00:00Z",
              recordsCollected: 44,
            },
            processing: {
              status: "completed",
              completedAt: "2026-06-24T10:15:00Z",
              recordCounts: { costFacts: 8 },
            },
          },
        ],
      };
    });

    render(<Admin />);

    expect(await screen.findByText("Subscription Overview")).toBeInTheDocument();
    expect(screen.getByText("Azure Sub")).toBeInTheDocument();
    expect(screen.getByText("Reader granted")).toBeInTheDocument();
    expect(screen.getByText("Advisor missing")).toBeInTheDocument();
    expect(screen.getByText("Records Collected")).toBeInTheDocument();
  });

  it("shows onboarding permission failures instead of silently collecting", async () => {
    apiMock.mockResolvedValue({
      status: "permission_validation_required",
      message: "Required Azure permissions are missing.",
      validationResults: [
        {
          subscriptionId: "sub-1",
          validationStatus: "failed",
          validationResults: {
            costManagement: {
              name: "costManagement",
              mandatory: true,
              status: "failed",
              message: "Cost Management Reader is missing",
              requiredPermission: "Cost Management Reader",
              whyRequired: "Required to collect Azure cost data.",
              approvalUrl: "https://portal.azure.com/",
              approver: "Azure subscription Owner can assign this role.",
            },
          },
        },
      ],
    });

    render(<Onboarding />);

    expect(await screen.findByText("Permission status")).toBeInTheDocument();
    expect(screen.getByText("Cost Management Reader")).toBeInTheDocument();
    expect(screen.getByText("Missing")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Microsoft approval page" })).toHaveAttribute(
      "href",
      "https://portal.azure.com/",
    );
  });
});
