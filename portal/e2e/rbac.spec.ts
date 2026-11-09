import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { loginAs } from "./helpers";

test.describe("RBAC Negative Testing", () => {
  test("Staff role: Export button is disabled in UI and direct export call returns 403", async ({
    page,
  }) => {
    // 1. Login with staff credentials
    await loginAs(page, "staff");
    // Verify staff role in localStorage
    const userRaw = await page.evaluate(() => localStorage.getItem("portal_user"));
    expect(userRaw).not.toBeNull();
    const user = JSON.parse(userRaw!);
    expect(user.username).toBe("staff");
    expect(user.role).toBe("staff");

    // Verify navbar displays staff role
    const navbarUser = page.locator('[data-testid="navbar-user"]');
    await expect(navbarUser).toBeVisible();
    await expect(navbarUser).toContainText("staff");

    // 2. Assert UI shows a disabled export button with explanatory tooltip for staff
    const exportBtn = page.locator('[data-testid="btn-export-csv"]');
    await expect(exportBtn).toBeVisible();
    await expect(exportBtn).toBeDisabled();
    const btnTitle = await exportBtn.getAttribute("title");
    expect(btnTitle).toContain("Staff role cannot trigger carrier export");

    // 3. Attempt the export through the portal proxy with the staff session
    const apiRes = await page.request.get("/api/backend/api/export/csv?carrier_id=kerry");

    // Assert backend returns 403 Forbidden, and a forged role changes nothing
    expect(apiRes.status()).toBe(403);
    const errBody = await apiRes.json();
    expect(errBody.detail).toContain("Owner permission required");
    const forged = await page.request.get("/api/backend/api/export/csv?carrier_id=kerry&role=owner", {
      headers: { "X-User-Role": "owner" },
    });
    expect(forged.status()).toBe(403);

    // 4. Test navigating directly to export URL as staff in the browser: returns 403 Forbidden
    const navRes = await page.goto("/api/backend/api/export/csv?carrier_id=kerry");
    expect(navRes?.status()).toBe(403);
    const navBody = await navRes?.json();
    expect(navBody.detail).toContain("Owner permission required");

    // Return to dashboard and ensure UI is healthy and intact
    await page.goto("/");
    await expect(page.locator("table")).toBeVisible();
    await expect(page.locator("nav")).toBeVisible();
    await expect(page.locator('[data-testid="btn-export-csv"]')).toBeDisabled();

    // Save RBAC network log evidence
    const rbacEvidence = {
      role: "staff",
      endpoint: "/api/export/csv?carrier_id=kerry",
      method: "GET",
      status: apiRes.status(),
      statusText: "Forbidden",
      responsePayload: errBody,
      uiDisabledVerified: true,
      navigation403Verified: true,
    };

    const evidenceDir = path.resolve(__dirname, "../../playwright-report");
    if (!fs.existsSync(evidenceDir)) fs.mkdirSync(evidenceDir, { recursive: true });
    fs.writeFileSync(
      path.join(evidenceDir, "rbac_negative_test_evidence.json"),
      JSON.stringify(rbacEvidence, null, 2),
      "utf-8"
    );
  });

  test("Owner role: Export button is enabled in UI and export succeeds", async ({ page }) => {
    // Login with owner credentials
    await loginAs(page, "owner");

    // Assert export button is enabled for owner
    const exportBtn = page.locator('[data-testid="btn-export-csv"]');
    await expect(exportBtn).toBeVisible();
    await expect(exportBtn).toBeEnabled();

    // Call export through the portal proxy as owner
    const apiRes = await page.request.get("/api/backend/api/export/csv?carrier_id=kerry");

    expect(apiRes.status()).toBe(200);
    const contentType = apiRes.headers()["content-type"];
    expect(contentType).toContain("text/csv");
  });
});
