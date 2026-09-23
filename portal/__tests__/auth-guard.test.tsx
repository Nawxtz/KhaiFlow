import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import DashboardLayout from "@/app/(dashboard)/layout";
import { I18nProvider } from "@/context/I18nContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { STORAGE_KEY_TOKEN, STORAGE_KEY_USER } from "@/lib/auth";

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/",
}));

describe("Auth Guard in DashboardLayout", () => {
  beforeEach(() => {
    localStorage.clear();
    mockPush.mockClear();
  });

  it("redirects unauthenticated users to /login and does not show dashboard content", async () => {
    render(
      <I18nProvider initialLocale="en">
        <ThemeProvider initialTheme="light">
          <DashboardLayout>
            <div data-testid="protected-content">Secret Seller Content</div>
          </DashboardLayout>
        </ThemeProvider>
      </I18nProvider>
    );

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/login");
    });

    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
  });

  it("renders protected dashboard content when a valid session token exists", async () => {
    localStorage.setItem(STORAGE_KEY_TOKEN, "valid_mock_token_123");
    localStorage.setItem(
      STORAGE_KEY_USER,
      JSON.stringify({ id: "user_owner", username: "owner", role: "owner" })
    );

    render(
      <I18nProvider initialLocale="en">
        <ThemeProvider initialTheme="light">
          <DashboardLayout>
            <div data-testid="protected-content">Secret Seller Content</div>
          </DashboardLayout>
        </ThemeProvider>
      </I18nProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("protected-content")).toBeInTheDocument();
    });

    expect(mockPush).not.toHaveBeenCalledWith("/login");
    expect(screen.getByTestId("btn-logout")).toBeInTheDocument();
  });
});
