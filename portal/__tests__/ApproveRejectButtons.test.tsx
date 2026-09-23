import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ApproveRejectButtons from "@/components/ApproveRejectButtons";
import { I18nProvider } from "@/context/I18nContext";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    approveOrder: vi.fn(),
    rejectOrder: vi.fn(),
  },
}));

vi.mock("@/lib/auth", () => ({
  getUser: vi.fn(() => ({
    id: "user_owner",
    username: "owner_tester",
    role: "owner",
  })),
}));

describe("ApproveRejectButtons Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderComponent(orderId = "order_test_123") {
    return render(
      <I18nProvider initialLocale="en">
        <ApproveRejectButtons orderId={orderId} />
      </I18nProvider>
    );
  }

  it("calls approveOrder API with order_id and reviewer_id when Approve button is clicked", async () => {
    vi.mocked(api.approveOrder).mockResolvedValueOnce({
      status: "approved",
      order_id: "order_test_123",
      order_status: "PAYMENT_RECEIVED",
      approval_state: "APPROVED",
      message: "Order payment approved manually by seller.",
    });

    renderComponent("order_test_123");

    const approveBtn = screen.getByTestId("btn-approve");
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(api.approveOrder).toHaveBeenCalledTimes(1);
      expect(api.approveOrder).toHaveBeenCalledWith("order_test_123", {
        reviewer_id: "owner_tester",
      });
    });

    expect(screen.getByTestId("action-feedback")).toBeInTheDocument();
  });

  it("opens reject modal, validates required reason, and calls rejectOrder API", async () => {
    vi.mocked(api.rejectOrder).mockResolvedValueOnce({
      status: "rejected",
      order_id: "order_test_123",
      order_status: "PAYMENT_RECONCILE",
      approval_state: "REJECTED_MANUAL",
      message: "Order payment rejected: Slip unreadable",
    });

    renderComponent("order_test_123");

    // Click Reject to open form
    const rejectBtn = screen.getByTestId("btn-reject");
    fireEvent.click(rejectBtn);

    expect(screen.getByTestId("reject-dialog")).toBeInTheDocument();

    // Try submitting without reason -> shows error
    const confirmBtn = screen.getByTestId("btn-confirm-reject");
    fireEvent.click(confirmBtn);

    expect(api.rejectOrder).not.toHaveBeenCalled();
    expect(screen.getByTestId("reject-error")).toBeInTheDocument();

    // Type reason and submit
    const input = screen.getByTestId("input-reject-reason");
    fireEvent.change(input, { target: { value: "Slip unreadable" } });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.rejectOrder).toHaveBeenCalledTimes(1);
      expect(api.rejectOrder).toHaveBeenCalledWith("order_test_123", {
        reviewer_id: "owner_tester",
        reason: "Slip unreadable",
      });
    });

    expect(screen.getByTestId("action-feedback")).toBeInTheDocument();
  });
});
