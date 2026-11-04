export interface NavItem {
  path: string;
  label: string;
}

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Overview" },
  { path: "/routing", label: "Routing Decisions" },
  { path: "/providers", label: "Providers & Models" },
  { path: "/tenants", label: "Tenants & Budgets" },
  { path: "/usage", label: "Usage & Cost" },
  { path: "/logs", label: "Request Logs" },
  { path: "/evaluation", label: "Evaluation" },
  { path: "/settings", label: "Settings" },
];
