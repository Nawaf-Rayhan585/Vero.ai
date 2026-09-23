import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { makeAuthValue } from "../test/authFixtures";
import { ApiError } from "../api/client";
import { LoginPage } from "./LoginPage";

describe("LoginPage", () => {
  it("submits email and password to auth.login", async () => {
    const authValue = makeAuthValue({ status: "signedOut" });
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { authValue });

    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(authValue.login).toHaveBeenCalledWith("owner@example.com", "password123");
  });

  it("shows the ApiError message on failure", async () => {
    const authValue = makeAuthValue({
      status: "signedOut",
      login: vi.fn().mockRejectedValue(new ApiError(401, "Unauthorized", "Incorrect email or password")),
    });
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { authValue });

    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Incorrect email or password")).toBeInTheDocument();
  });

  it("shows a generic message for a non-ApiError failure (e.g. the backend is unreachable)", async () => {
    const authValue = makeAuthValue({ status: "signedOut", login: vi.fn().mockRejectedValue(new Error("boom")) });
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { authValue });

    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText(/Could not sign in/)).toBeInTheDocument();
  });

  it("links to the register page", () => {
    renderWithProviders(<LoginPage />, { authValue: makeAuthValue({ status: "signedOut" }) });
    expect(screen.getByRole("link", { name: "Create one" })).toHaveAttribute("href", "/register");
  });
});
