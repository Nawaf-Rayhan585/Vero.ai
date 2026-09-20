import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { SettingsProvider } from "../settings/SettingsContext";

export function renderWithProviders(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  const result = render(
    <QueryClientProvider client={queryClient}>
      <SettingsProvider>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </SettingsProvider>
    </QueryClientProvider>,
  );

  return { ...result, queryClient };
}
