import { test, expect } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

test.describe("Core Workflows & API Integration", () => {
  test.beforeEach(async ({ page }) => {
    // Authenticate as owner before each test
    await page.addInitScript(() => {
      localStorage.setItem("portal_session_token", "mock_session_token_workflow_test");
      localStorage.setItem(
        "portal_user",
        JSON.stringify({ id: "seller_owner", username: "owner", role: "owner" })
      );
    });
  });

  test("Dashboard Load: renders order table and verified status badge colours", async ({ page }) => {
    await page.goto("/");

    // Wait for table to load
    const table = page.locator("table");
    await expect(table).toBeVisible({ timeout: 10000 });

    // Assert rows exist
    const rows = page.locator("tbody tr");
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThanOrEqual(1);

    // Verify status badges exist and inspect their color classes
    const badges = page.locator('[data-testid="order-status-badge"]');
    const badgeCount = await badges.count();
    expect(badgeCount).toBeGreaterThan(0);

    let hasAwaitingPayment = false;
    let hasFulfilled = false;

    for (let i = 0; i < badgeCount; i++) {
      const badge = badges.nth(i);
      const status = await badge.getAttribute("data-status");
      const badgeClass = await badge.getAttribute("class");

      if (status === "AWAITING_PAYMENT") {
        hasAwaitingPayment = true;
        // Verify yellow badge styling
        expect(badgeClass).toContain("bg-yellow-100");
        expect(badgeClass).toContain("text-yellow-800");
      } else if (status === "FULFILLED") {
        hasFulfilled = true;
        // Verify green badge styling
        expect(badgeClass).toContain("bg-green-100");
        expect(badgeClass).toContain("text-green-800");
      }
    }

    console.log(`[DASHBOARD BADGES] AWAITING_PAYMENT found: ${hasAwaitingPayment}, FULFILLED found: ${hasFulfilled}`);
    expect(hasAwaitingPayment).toBe(true);
    expect(hasFulfilled).toBe(true);
  });

  test("Inventory Page: renders SKU items and accurate available stock calculations", async ({ page }) => {
    await page.goto("/inventory");

    const table = page.locator("table");
    await expect(table).toBeVisible({ timeout: 10000 });

    // Row 1: TSHIRT-M -> stock 50, reserved 1, available = 49 (50 - 1)
    const tshirtRow = page.locator('[data-testid="inventory-row-TSHIRT-M"]');
    await expect(tshirtRow).toBeVisible();
    await expect(tshirtRow).toContainText("TSHIRT-M");
    // Available stock column (7th column in row: SKU, Name, Category, Price, Stock, Reserved, Available, Status)
    const tshirtAvailable = tshirtRow.locator("td").nth(6);
    await expect(tshirtAvailable).toHaveText("49");

    // Row 2: MUG-001 -> stock 30, reserved 0, available = 30
    const mugRow = page.locator('[data-testid="inventory-row-MUG-001"]');
    await expect(mugRow).toBeVisible();
    await expect(mugRow).toContainText("MUG-001");
    const mugAvailable = mugRow.locator("td").nth(6);
    await expect(mugAvailable).toHaveText("30");

    // Row 3: TOTE-001 -> stock 40, reserved 1, available = 39
    const toteRow = page.locator('[data-testid="inventory-row-TOTE-001"]');
    await expect(toteRow).toBeVisible();
    await expect(toteRow).toContainText("TOTE-001");
    const toteAvailable = toteRow.locator("td").nth(6);
    await expect(toteAvailable).toHaveText("39");

    // Screenshot inventory table with available stock values
    await page.screenshot({
      path: path.resolve(__dirname, "../../playwright-screenshots/05-inventory-stock-table.png"),
      fullPage: true,
    });
  });

  test("Option B Flow: Approve payment for order awaiting seller approval", async ({ page }) => {
    const mockOrderApproval = {
      id: "ORD-MOCK-APPROVAL",
      shop_id: "default",
      line_user_id: "U_demo_buyer_option_b",
      status: "AWAITING_SELLER_APPROVAL",
      total: "780.00",
      currency: "THB",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      ttl_expires_at: null,
      approval_state: "AWAITING_SELLER_APPROVAL",
      payment_ref: "PROMPT_PAY_SLIP_998877",
      risk_score: 35,
      items: [
        {
          id: 991,
          order_id: "ORD-MOCK-APPROVAL",
          shop_id: "default",
          sku: "TSHIRT-M",
          name: "Minimalist Cotton T-Shirt (S/M/L)",
          size: "M",
          qty: 2,
          unit_price: "390.00",
          line_total: "780.00",
        },
      ],
    };

    // Route order detail API
    let approveRequestPayload: any = null;
    let approveIntercepted = false;

    await page.route("**/api/orders/ORD-MOCK-APPROVAL*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockOrderApproval),
      });
    });

    // Intercept approve endpoint
    await page.route("**/api/verification/approve/ORD-MOCK-APPROVAL*", async (route) => {
      approveIntercepted = true;
      approveRequestPayload = JSON.parse(route.request().postData() || "{}");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "approved",
          order_id: "ORD-MOCK-APPROVAL",
          order_status: "PAYMENT_RECEIVED",
          approval_state: "APPROVED",
          message: "Payment successfully approved",
        }),
      });
    });

    // Navigate directly to detail page
    await page.goto("/orders/ORD-MOCK-APPROVAL");

    // Verify detail elements
    await expect(page.locator("h1")).toContainText("ORD-MOCK-APPROVAL");
    await expect(page.locator('[data-testid="order-approval-state"]')).toHaveText("AWAITING_SELLER_APPROVAL");
    await expect(page.locator('[data-testid="order-risk-score"]')).toHaveText("35");
    await expect(page.locator('[data-testid="order-payment-ref"]')).toHaveText("PROMPT_PAY_SLIP_998877");

    // Click Approve
    const approveBtn = page.locator('[data-testid="btn-approve"]');
    await expect(approveBtn).toBeVisible();
    await approveBtn.click();

    // Assert network request was sent
    expect(approveIntercepted).toBe(true);
    expect(approveRequestPayload).toEqual({ reviewer_id: "owner" });

    // Assert UI updates with feedback
    const feedback = page.locator('[data-testid="action-feedback"]');
    await expect(feedback).toBeVisible();

    // Log evidence
    const evidence = {
      action: "APPROVE",
      endpoint: "/api/verification/approve/ORD-MOCK-APPROVAL",
      method: "POST",
      status: 200,
      requestPayload: approveRequestPayload,
      feedbackText: (await feedback.textContent())?.trim(),
    };
    console.log("[OPTION B APPROVE EVIDENCE]:", JSON.stringify(evidence, null, 2));

    const evidenceDir = path.resolve(__dirname, "../../playwright-report");
    if (!fs.existsSync(evidenceDir)) fs.mkdirSync(evidenceDir, { recursive: true });
    fs.writeFileSync(
      path.join(evidenceDir, "option_b_approve_evidence.json"),
      JSON.stringify(evidence, null, 2),
      "utf-8"
    );
  });

  test("Reject Modal: validates reason requirement and fires reject API", async ({ page }) => {
    const mockOrderApproval = {
      id: "ORD-MOCK-REJECT",
      shop_id: "default",
      line_user_id: "U_demo_buyer_option_b",
      status: "AWAITING_SELLER_APPROVAL",
      total: "390.00",
      currency: "THB",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      approval_state: "AWAITING_SELLER_APPROVAL",
      payment_ref: "SLIP_UNREADABLE_1122",
      risk_score: 85,
      items: [
        {
          id: 992,
          order_id: "ORD-MOCK-REJECT",
          sku: "TSHIRT-M",
          name: "Minimalist Cotton T-Shirt (S/M/L)",
          size: "S",
          qty: 1,
          unit_price: "390.00",
          line_total: "390.00",
        },
      ],
    };

    let rejectRequestPayload: any = null;
    let rejectIntercepted = false;

    await page.route("**/api/orders/ORD-MOCK-REJECT*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockOrderApproval),
      });
    });

    await page.route("**/api/verification/reject/ORD-MOCK-REJECT*", async (route) => {
      rejectIntercepted = true;
      rejectRequestPayload = JSON.parse(route.request().postData() || "{}");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "rejected",
          order_id: "ORD-MOCK-REJECT",
          order_status: "CANCELLED",
          approval_state: "REJECTED",
          message: "Payment successfully rejected",
        }),
      });
    });

    await page.goto("/orders/ORD-MOCK-REJECT");
    await expect(page.locator("h1")).toContainText("ORD-MOCK-REJECT");

    // 1. Click Reject button to open dialog
    const rejectBtn = page.locator('[data-testid="btn-reject"]');
    await expect(rejectBtn).toBeVisible();
    await rejectBtn.click();

    // 2. Assert modal/dialog opens
    const dialog = page.locator('[data-testid="reject-dialog"]');
    await expect(dialog).toBeVisible();

    // 3. Assert submit button is disabled without reason
    const confirmRejectBtn = page.locator('[data-testid="btn-confirm-reject"]');
    await expect(confirmRejectBtn).toBeDisabled();

    // 4. Type a rejection reason
    const reasonInput = page.locator('[data-testid="input-reject-reason"]');
    await reasonInput.fill("Slip QR code is unreadable and amount does not match order");

    // 5. Assert button becomes enabled
    await expect(confirmRejectBtn).toBeEnabled();

    // 6. Click submit
    await confirmRejectBtn.click();

    // 7. Assert API call was fired with correct payload
    expect(rejectIntercepted).toBe(true);
    expect(rejectRequestPayload).toEqual({
      reviewer_id: "owner",
      reason: "Slip QR code is unreadable and amount does not match order",
    });

    // 8. Assert dialog closed and UI feedback updated
    await expect(dialog).not.toBeVisible();
    const feedback = page.locator('[data-testid="action-feedback"]');
    await expect(feedback).toBeVisible();

    const evidence = {
      action: "REJECT",
      endpoint: "/api/verification/reject/ORD-MOCK-REJECT",
      method: "POST",
      status: 200,
      requestPayload: rejectRequestPayload,
      feedbackText: (await feedback.textContent())?.trim(),
    };
    console.log("[OPTION B REJECT EVIDENCE]:", JSON.stringify(evidence, null, 2));

    const evidenceDir = path.resolve(__dirname, "../../playwright-report");
    if (!fs.existsSync(evidenceDir)) fs.mkdirSync(evidenceDir, { recursive: true });
    fs.writeFileSync(
      path.join(evidenceDir, "option_b_reject_evidence.json"),
      JSON.stringify(evidence, null, 2),
      "utf-8"
    );
  });
});
