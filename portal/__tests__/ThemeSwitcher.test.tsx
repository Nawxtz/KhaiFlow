import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ThemeSwitcher from "@/components/ThemeSwitcher";
import { ThemeProvider } from "@/context/ThemeContext";
import { I18nProvider } from "@/context/I18nContext";

describe("ThemeSwitcher Component", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("toggles between light and dark themes and updates the DOM class and localStorage", () => {
    render(
      <I18nProvider initialLocale="en">
        <ThemeProvider initialTheme="light">
          <ThemeSwitcher />
        </ThemeProvider>
      </I18nProvider>
    );

    // Initial state: light mode (no 'dark' class)
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    // Click theme switcher to toggle to dark mode
    const switcher = screen.getByTestId("theme-switcher");
    fireEvent.click(switcher);

    // DOM documentElement must contain 'dark' class
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("user_prefs_theme")).toBe("dark");

    // Click again to toggle back to light mode
    fireEvent.click(switcher);

    // 'dark' class must be removed
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("user_prefs_theme")).toBe("light");
  });
});
