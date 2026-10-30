import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { FindingDrawer } from "../components/FindingDrawer";

/** Renders a page inside the app's providers, with the finding drawer mounted. */
export function renderPage(page: ReactElement, url = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="*" element={<>{page}<FindingDrawer /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Stubs fetch with a map of "METHOD /path" (or "/path" for GET) to JSON bodies. */
export function mockApi(routes: Record<string, unknown | ((init?: RequestInit) => unknown)>) {
  const calls: { method: string; path: string; body?: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = input.split("?")[0];
    calls.push({ method, path, body: init?.body as string | undefined });
    const handler = routes[`${method} ${path}`] ?? routes[path];
    if (handler === undefined) return new Response(JSON.stringify({ detail: "not mocked" }), { status: 404 });
    const body = typeof handler === "function" ? (handler as (i?: RequestInit) => unknown)(init) : handler;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  return calls;
}
