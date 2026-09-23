import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import OrderTable from "@/components/OrderTable";
import { I18nProvider } from "@/context/I18nContext";
import { Order } from "@/lib/api";

const mockOrders: Order[] = [
  {
    id: "ord_001",
    line_user_id: "U123456",
    status: "NOT_STARTED",
    total: "150.00",
    currency: "THB",
    created_at: "2026-09-23T10:00:00Z",
    updated_at: "2026-09-23T10:00:00Z",
    items: [
      {
        id: 1,
        order_id: "ord_001",
        sku: "SKU1",
        name: "Product 1",
        qty: 1,
        unit_price: "150.00",
        line_total: "150.00",
      },
    ],
  },
  {
    id: "ord_002",
    line_user_id: "U234567",
    status: "AWAITING_PAYMENT",
    total: "250.00",
    currency: "THB",
    created_at: "2026-09-23T11:00:00Z",
    updated_at: "2026-09-23T11:00:00Z",
  },
  {
    id: "ord_003",
    line_user_id: "U345678",
    status: "PAYMENT_RECEIVED",
    total: "350.00",
    currency: "THB",
    created_at: "2026-09-23T12:00:00Z",
    updated_at: "2026-09-23T12:00:00Z",
  },
  {
    id: "ord_004",
    line_user_id: "U456789",
    status: "FULFILLED",
    total: "450.00",
    currency: "THB",
    created_at: "2026-09-23T13:00:00Z",
    updated_at: "2026-09-23T13:00:00Z",
  },
  {
    id: "ord_005",
    line_user_id: "U567890",
    status: "PAYMENT_RECONCILE",
    total: "550.00",
    currency: "THB",
    created_at: "2026-09-23T14:00:00Z",
    updated_at: "2026-09-23T14:00:00Z",
  },
];

function renderWithI18n(ui: React.ReactElement, initialLocale: "th" | "en" = "th") {
  return render(<I18nProvider initialLocale={initialLocale}>{ui}</I18nProvider>);
}

describe("OrderTable Component", () => {
  it("renders order list with all orders and correct IDs", () => {
    renderWithI18n(<OrderTable orders={mockOrders} />);

    expect(screen.getByText("ord_001")).toBeInTheDocument();
    expect(screen.getByText("ord_002")).toBeInTheDocument();
    expect(screen.getByText("ord_003")).toBeInTheDocument();
    expect(screen.getByText("ord_004")).toBeInTheDocument();
    expect(screen.getByText("ord_005")).toBeInTheDocument();
  });

  it("renders correct status badge colours for each status", () => {
    renderWithI18n(<OrderTable orders={mockOrders} />);

    const badges = screen.getAllByTestId("order-status-badge");
    expect(badges).toHaveLength(5);

    // NOT_STARTED -> grey
    expect(badges[0]).toHaveAttribute("data-status", "NOT_STARTED");
    expect(badges[0].className).toContain("bg-gray-100");

    // AWAITING_PAYMENT -> yellow
    expect(badges[1]).toHaveAttribute("data-status", "AWAITING_PAYMENT");
    expect(badges[1].className).toContain("bg-yellow-100");

    // PAYMENT_RECEIVED -> blue
    expect(badges[2]).toHaveAttribute("data-status", "PAYMENT_RECEIVED");
    expect(badges[2].className).toContain("bg-blue-100");

    // FULFILLED -> green
    expect(badges[3]).toHaveAttribute("data-status", "FULFILLED");
    expect(badges[3].className).toContain("bg-green-100");

    // PAYMENT_RECONCILE -> red
    expect(badges[4]).toHaveAttribute("data-status", "PAYMENT_RECONCILE");
    expect(badges[4].className).toContain("bg-red-100");
  });

  it("renders empty state when orders list is empty", () => {
    renderWithI18n(<OrderTable orders={[]} />);

    const emptyBox = screen.getByTestId("order-table-empty");
    expect(emptyBox).toBeInTheDocument();
  });

  it("renders loading state when isLoading is true", () => {
    renderWithI18n(<OrderTable orders={[]} isLoading={true} />);

    const loadingBox = screen.getByTestId("order-table-loading");
    expect(loadingBox).toBeInTheDocument();
  });

  it("renders error state when error is provided", () => {
    renderWithI18n(<OrderTable orders={[]} error="Network failure" />);

    const errorBox = screen.getByTestId("order-table-error");
    expect(errorBox).toBeInTheDocument();
    expect(errorBox).toHaveTextContent("Network failure");
  });
});
