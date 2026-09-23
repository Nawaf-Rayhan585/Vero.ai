import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { SettingsProvider } from "../settings/SettingsContext";
import { AuthContext, type AuthContextValue } from "../auth/AuthContext";
import { makeAuthValue } from "./authFixtures";

export function renderWithProviders(
  ui: ReactElement,
  { route = "/", authValue }: { route?: string; authValue?: AuthContextValue } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  const result = render(
    <QueryClientProvider client={queryClient}>
      {/* A plain fake context value, not the real AuthProvider: the real one's mount effect
          touches the secure store and the network, which every existing render would then
          need to account for. Tests that care about a specific auth state pass `authValue`
          (see src/test/authFixtures.ts); everything else gets a harmless signed-in default. */}
      <AuthContext.Provider value={authValue ?? makeAuthValue()}>
        <SettingsProvider>
          <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
        </SettingsProvider>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );

  return { ...result, queryClient };
}
