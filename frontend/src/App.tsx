import { lazy, Suspense, type ReactNode } from "react";
import { Route, Routes } from "react-router";
import { RequireAdmin } from "./components/Auth";
import { Layout } from "./components/Layout";
import { EmptyState, LoadingState } from "./components/States";

// Pages load on demand, so the chart library only downloads for pages that draw charts.
const Overview = lazy(() => import("./pages/Overview").then((m) => ({ default: m.Overview })));
const RoutingDecisions = lazy(() => import("./pages/RequestLogs").then((m) => ({ default: m.RoutingDecisions })));
const RequestLogs = lazy(() => import("./pages/RequestLogs").then((m) => ({ default: m.RequestLogs })));
const Providers = lazy(() => import("./pages/Providers").then((m) => ({ default: m.Providers })));
const Tenants = lazy(() => import("./pages/Tenants").then((m) => ({ default: m.Tenants })));
const Usage = lazy(() => import("./pages/Usage").then((m) => ({ default: m.Usage })));
const Evaluation = lazy(() => import("./pages/Evaluation").then((m) => ({ default: m.Evaluation })));
const Settings = lazy(() => import("./pages/Settings").then((m) => ({ default: m.Settings })));

const page = (node: ReactNode, { admin = true } = {}) => (
  <Suspense fallback={<LoadingState />}>{admin ? <RequireAdmin>{node}</RequireAdmin> : node}</Suspense>
);

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={page(<Overview />)} />
        <Route path="routing" element={page(<RoutingDecisions />)} />
        {/* Backed by public read-only endpoints: no admin session needed. */}
        <Route path="providers" element={page(<Providers />, { admin: false })} />
        <Route path="tenants" element={page(<Tenants />)} />
        <Route path="usage" element={page(<Usage />)} />
        <Route path="logs" element={page(<RequestLogs />)} />
        <Route path="evaluation" element={page(<Evaluation />)} />
        <Route path="settings" element={page(<Settings />)} />
        <Route path="*" element={<EmptyState title="Page not found" />} />
      </Route>
    </Routes>
  );
}
