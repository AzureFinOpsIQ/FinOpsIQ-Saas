import { describe, expect, it, vi } from "vitest";
import {
  classifyService,
  formatDateTime,
  formatMoney,
  freshnessLabel,
  humanize,
  recommendationNarrative,
  recommendationTitle,
  riskFor,
} from "@/lib/finops-ui";

describe("FinOps presentation helpers", () => {
  it("formats money and datetimes for business reporting", () => {
    expect(formatMoney(1250, "INR")).toContain("1,250");
    expect(formatMoney(null, "INR")).toContain("0");
    expect(formatDateTime(undefined)).toBe("Not available");
    expect(formatDateTime("not-a-date")).toBe("Not available");
    expect(formatDateTime("2026-06-24T10:00:00Z")).not.toBe("Not available");
  });

  it("classifies data freshness from status and timestamps", () => {
    vi.setSystemTime(new Date("2026-06-24T10:00:00Z"));
    expect(freshnessLabel("2026-06-24T08:00:00Z", "ready").label).toBe("Fresh");
    expect(freshnessLabel("2026-06-20T08:00:00Z", "ready").label).toBe("Stale");
    expect(freshnessLabel(undefined, "collection_failed").label).toBe("Collection Failed");
    vi.useRealTimers();
  });

  it("classifies services, risk, and recommendation narratives", () => {
    expect(classifyService("Virtual Machines")).toBe("Compute");
    expect(classifyService("Virtual Network Gateway")).toBe("Networking");
    expect(classifyService("Azure Storage")).toBe("Storage");
    expect(classifyService("Azure Cosmos DB")).toBe("Databases");
    expect(classifyService("Azure OpenAI")).toBe("AI Services");
    expect(classifyService("Other Service")).toBe("Other");

    expect(riskFor("idle_public_ip", 10)).toBe("Low");
    expect(riskFor("aks", 100)).toBe("Low to Medium");
    expect(riskFor("storage", 50)).toBe("Medium");

    expect(humanize("idle_public-ip")).toBe("Idle Public Ip");
    expect(recommendationTitle({ category: "idle_public_ip" })).toBe(
      "Unused Public IP Detected",
    );
    expect(recommendationTitle({ category: "aks_rightsizing" })).toBe(
      "AKS Cluster Overprovisioned",
    );

    const idle = recommendationNarrative({ category: "idle_public_ip" });
    expect(idle.action).toContain("Delete the public IP");
    const aks = recommendationNarrative({
      category: "aks",
      evidence: { cpuAverage: 4.2 },
    });
    expect(aks.why).toContain("4.2% CPU");
    const generic = recommendationNarrative({ content: "Review reserved instances" });
    expect(generic.action).toContain("Review reserved instances");
  });
});
