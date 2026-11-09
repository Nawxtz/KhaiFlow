import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import DemoBanner from "@/components/DemoBanner";
import { I18nProvider } from "@/context/I18nContext";

describe("DemoBanner", () => {
  it("states the required disclaimer in English", () => {
    render(
      <I18nProvider initialLocale="en">
        <DemoBanner />
      </I18nProvider>
    );

    expect(screen.getByTestId("demo-banner")).toHaveTextContent(
      "Demonstration system. Not licensed to process payments. Real deployment requires merchant onboarding and legal review."
    );
  });

  it("has a Thai version", () => {
    render(
      <I18nProvider initialLocale="th">
        <DemoBanner />
      </I18nProvider>
    );

    expect(screen.getByTestId("demo-banner")).toHaveTextContent("ระบบสาธิต");
  });
});
