import { describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { Sidebar } from "../components/layout/Sidebar";
import { NotFoundPage } from "../pages/NotFoundPage";
import { APP_ROUTES } from "./routes";

function TestApp() {
  return (
    <>
      <Sidebar />
      <Routes>
        {APP_ROUTES.map((route) => (
          <Route key={route.path} path={route.path} element={route.element} />
        ))}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  );
}

describe("app routing", () => {
  it("the sidebar lists every configured route exactly once", () => {
    renderWithProviders(<TestApp />);
    const nav = screen.getByRole("navigation", { name: /main navigation/i });
    for (const route of APP_ROUTES) {
      expect(within(nav).getByRole("link", { name: route.navLabel })).toBeInTheDocument();
    }
    expect(within(nav).getAllByRole("link")).toHaveLength(APP_ROUTES.length);
  });

  it("marks the active route with aria-current and navigates to placeholder pages", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TestApp />);

    // Account is still an honest placeholder naming the phase that builds it.
    await user.click(screen.getByRole("link", { name: "Account" }));

    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "Account" })).toBeInTheDocument();
    expect(screen.getByText(/Phase 10/)).toBeInTheDocument();
  });

  it("Events and Analytics are real pages now, not placeholders", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TestApp />);

    await user.click(screen.getByRole("link", { name: "Events" }));
    expect(screen.getByRole("heading", { name: "Events" })).toBeInTheDocument();
    expect(screen.queryByText(/Phase 9/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Analytics" }));
    expect(screen.getByRole("heading", { name: "Analytics" })).toBeInTheDocument();
    expect(screen.queryByText(/Phase 9/)).not.toBeInTheDocument();
  });

  it("renders NotFoundPage for an unknown path", () => {
    renderWithProviders(<TestApp />, { route: "/does-not-exist" });
    expect(screen.getByText("That page doesn't exist.")).toBeInTheDocument();
  });
});
