import "@testing-library/jest-dom/vitest";
import React from "react";
import { vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => (globalThis as { __mockPathname?: string }).__mockPathname ?? "/dashboard",
  useRouter: () => ({
    push: (globalThis as { __mockRouterPush?: (path: string) => void }).__mockRouterPush ?? vi.fn(),
  }),
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({
    theme: "light",
    setTheme: vi.fn(),
  }),
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("recharts", () => {
  const Chart = ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="chart">{children}</div>
  );
  const Element = () => <div />;
  return {
    Area: Element,
    AreaChart: Chart,
    Bar: Element,
    BarChart: Chart,
    CartesianGrid: Element,
    Cell: Element,
    Legend: Element,
    Line: Element,
    LineChart: Chart,
    Pie: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    PieChart: Chart,
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => (
      <div data-testid="responsive-container">{children}</div>
    ),
    Tooltip: Element,
    XAxis: Element,
    YAxis: Element,
  };
});
