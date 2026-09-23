import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { makeAuthValue } from "../test/authFixtures";
import { ApiError } from "../api/client";
import { RegisterPage } from "./RegisterPage";

describe("RegisterPage", () => {
  it("submits all fields to auth.register", async () => {
    const authValue = makeAuthValue({ status: "signedOut" });
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />, { authValue });

    await user.type(screen.getByLabelText("Your name"), "Jane Doe");
    await user.type(screen.getByLabelText("Email"), "jane@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.type(screen.getByLabelText("Organization name"), "Acme Retail");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(authValue.register).toHaveBeenCalledWith("jane@example.com", "password123", "Jane Doe", "Acme Retail");
  });

  it("shows the ApiError message on failure", async () => {
    const authValue = makeAuthValue({
      status: "signedOut",
      register: vi
        .fn()
        .mockRejectedValue(new ApiError(409, "Conflict", "An account with this email already exists")),
    });
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />, { authValue });

    await user.type(screen.getByLabelText("Your name"), "Jane Doe");
    await user.type(screen.getByLabelText("Email"), "jane@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.type(screen.getByLabelText("Organization name"), "Acme Retail");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("An account with this email already exists")).toBeInTheDocument();
  });

  it("enforces the minimum password length client-side", () => {
    renderWithProviders(<RegisterPage />, { authValue: makeAuthValue({ status: "signedOut" }) });
    expect(screen.getByLabelText("Password")).toHaveAttribute("minlength", "10");
  });

  it("links to the login page", () => {
    renderWithProviders(<RegisterPage />, { authValue: makeAuthValue({ status: "signedOut" }) });
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });
});
