import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import LoginPage from "@/app/login/page";
import { PageHeader } from "@/components/page";
import {
  ChartSkeleton,
  MetricSkeletonGrid,
  StatusPill,
  TableSkeleton,
} from "@/components/ux";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

describe("shared UI components", () => {
  it("renders button, card, input, and page header semantics", () => {
    render(
      <Card data-testid="card" className="custom-card">
        <PageHeader title="Costs" description="Analyze spend" />
        <Input aria-label="Search resources" defaultValue="aks" />
        <Button>Apply</Button>
      </Card>,
    );

    expect(screen.getByTestId("card")).toHaveClass("custom-card");
    expect(screen.getByRole("heading", { name: "Costs" })).toBeInTheDocument();
    expect(screen.getByText("Analyze spend")).toBeInTheDocument();
    expect(screen.getByLabelText("Search resources")).toHaveValue("aks");
    expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled();
  });

  it("renders loading skeletons with requested shapes", () => {
    const { container } = render(
      <>
        <MetricSkeletonGrid count={2} />
        <ChartSkeleton message="Loading cost chart" />
        <TableSkeleton rows={2} columns={3} />
        <StatusPill label="Granted" tone="bg-green-100 text-green-800" />
      </>,
    );

    expect(screen.getByText("Loading cost chart")).toBeInTheDocument();
    expect(screen.getByText("Granted")).toHaveClass("bg-green-100");
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(10);
  });
});

describe("public landing and login pages", () => {
  it("renders the SaaS landing page content and sign-in links", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { name: "AI-Powered Azure FinOps Platform" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Cost Analytics")).toBeInTheDocument();
    expect(screen.getByText("Microsoft Entra ID Authentication")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /sign in/i })[0]).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("starts Microsoft sign-in from the login page", () => {
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "" },
    });
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<LoginPage />);
    const button = screen.getByRole("button", { name: /sign in with microsoft/i });

    fireEvent.click(button);

    expect(window.location.href).toBe("/api/auth/login");
    expect(button).toBeDisabled();

    errorSpy.mockRestore();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });
});
