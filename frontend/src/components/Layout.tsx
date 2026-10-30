import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, Lightbulb, ListChecks, FileText, ShieldCheck } from "lucide-react";
import { FindingDrawer } from "./FindingDrawer";

const nav = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/insights", label: "Insights", icon: Lightbulb },
  { to: "/findings", label: "Findings", icon: ListChecks },
  { to: "/reports", label: "Reports", icon: FileText },
];

export function Layout() {
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-panel md:flex">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white">
            <ShieldCheck className="h-4.5 w-4.5" aria-hidden />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-ink">IT Audit Insights</p>
            <p className="text-xs text-muted">AGO annual reports</p>
          </div>
        </div>
        <nav className="flex flex-col gap-0.5 px-3">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${
                  isActive ? "bg-brand-soft font-medium text-brand" : "text-ink-soft hover:bg-canvas"
                }`
              }
            >
              <Icon className="h-4 w-4" aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 flex-1">
        {/* Compact nav for narrow screens */}
        <nav className="flex gap-1 overflow-x-auto border-b border-line bg-panel px-4 py-2 md:hidden">
          {nav.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-brand-soft text-brand" : "text-ink-soft"}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-8">
          <Outlet />
        </main>
      </div>
      <FindingDrawer />
    </div>
  );
}
