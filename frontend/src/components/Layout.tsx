import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { NAV_ITEMS } from "../pages/nav";
import { useSession } from "../hooks/useSession";
import { DemoBanner } from "./DemoBanner";

export function Layout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const health = useApi(api.health);
  const signedIn = Boolean(useSession());

  return (
    <div className="min-h-dvh bg-canvas text-ink">
      {health.status === "success" && health.data.simulated_only ? <DemoBanner /> : null}

      <header className="flex items-center justify-between border-b border-line bg-surface px-4 py-3 lg:hidden">
        <span className="font-semibold">RouteWise AI</span>
        <button
          type="button"
          aria-expanded={menuOpen}
          aria-controls="sidebar"
          onClick={() => setMenuOpen((open) => !open)}
          className="rounded-md border border-line px-3 py-1.5 text-sm"
        >
          {menuOpen ? "Close" : "Menu"}
        </button>
      </header>

      <div className="lg:flex">
        <nav
          id="sidebar"
          aria-label="Main"
          className={`${menuOpen ? "block" : "hidden"} border-b border-line bg-surface lg:block lg:min-h-dvh lg:w-60 lg:shrink-0 lg:border-r lg:border-b-0`}
        >
          <div className="hidden px-5 py-5 lg:block">
            <p className="font-semibold">RouteWise AI</p>
            <p className="text-xs text-muted">Intelligent LLM gateway</p>
          </div>
          <ul className="space-y-0.5 p-2">
            {NAV_ITEMS.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  end={item.path === "/"}
                  onClick={() => setMenuOpen(false)}
                  className={({ isActive }) =>
                    `block rounded-md px-3 py-2 text-sm ${
                      isActive ? "bg-accent/10 font-medium text-accent" : "text-muted hover:bg-sunken hover:text-ink"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
          {signedIn ? (
            <div className="border-t border-line p-2">
              <button
                type="button"
                onClick={api.logout}
                className="w-full rounded-md px-3 py-2 text-left text-sm text-muted hover:bg-sunken hover:text-ink"
              >
                Sign out
              </button>
            </div>
          ) : null}
        </nav>

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
