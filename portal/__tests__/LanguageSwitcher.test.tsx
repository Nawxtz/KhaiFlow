import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { I18nProvider, useI18n } from "@/context/I18nContext";

function TestApp() {
  const { t } = useI18n();
  return (
    <div>
      <LanguageSwitcher />
      <h1 data-testid="title">{t("orders_title")}</h1>
      <p data-testid="btn-label">{t("login_button")}</p>
      <span data-testid="status">{t("status_FULFILLED")}</span>
    </div>
  );
}

describe("LanguageSwitcher Component", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("toggles all visible strings between Thai and English and persists in localStorage", () => {
    render(
      <I18nProvider initialLocale="th">
        <TestApp />
      </I18nProvider>
    );

    // Initial state: Thai
    expect(screen.getByTestId("title")).toHaveTextContent("รายการคำสั่งซื้อ");
    expect(screen.getByTestId("btn-label")).toHaveTextContent("เข้าสู่ระบบ");
    expect(screen.getByTestId("status")).toHaveTextContent("จัดส่งเรียบร้อย");

    // Click language switcher to switch to English
    const switcher = screen.getByTestId("language-switcher");
    fireEvent.click(switcher);

    // Visible strings must update to English
    expect(screen.getByTestId("title")).toHaveTextContent("Order Dashboard");
    expect(screen.getByTestId("btn-label")).toHaveTextContent("Sign In");
    expect(screen.getByTestId("status")).toHaveTextContent("Fulfilled");
    expect(localStorage.getItem("user_prefs_language")).toBe("en");

    // Click language switcher again to switch back to Thai
    fireEvent.click(switcher);

    // Visible strings must update back to Thai
    expect(screen.getByTestId("title")).toHaveTextContent("รายการคำสั่งซื้อ");
    expect(screen.getByTestId("btn-label")).toHaveTextContent("เข้าสู่ระบบ");
    expect(screen.getByTestId("status")).toHaveTextContent("จัดส่งเรียบร้อย");
    expect(localStorage.getItem("user_prefs_language")).toBe("th");
  });
});
