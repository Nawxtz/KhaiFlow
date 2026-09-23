import { test, expect } from "@playwright/test";
import * as path from "path";

test.describe("Auth Guard & Security", () => {
  test.beforeEach(async ({ page }) => {
    // Clear localStorage to ensure clean state
    await page.goto("/login");
    await page.evaluate(() => localStorage.clear());
  });

  test("Visit / unauthenticated redirects to /login", async ({ page }) => {
    await page.goto("/");
    await page.waitForURL("**/login");
    expect(page.url()).toContain("/login");
    
    // Check that login form elements are visible
    await expect(page.locator('[data-testid="input-username"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-password"]')).toBeVisible();
    await expect(page.locator('[data-testid="btn-login"]')).toBeVisible();

    // Screenshot unauthenticated redirect
    await page.screenshot({
      path: path.resolve(__dirname, "../../playwright-screenshots/01-login-unauthenticated-redirect.png"),
      fullPage: true,
    });
  });

  test("Visit /inventory unauthenticated redirects to /login", async ({ page }) => {
    await page.goto("/inventory");
    await page.waitForURL("**/login");
    expect(page.url()).toContain("/login");
    await expect(page.locator('[data-testid="input-username"]')).toBeVisible();
  });

  test("Login with owner credentials redirects to Dashboard and persists session token", async ({ page }) => {
    await page.goto("/login");

    // Capture network requests during login
    const loginLogs: Array<{ url: string; method: string; status?: number }> = [];
    page.on("request", (req) => {
      loginLogs.push({ url: req.url(), method: req.method() });
    });
    page.on("response", (res) => {
      const idx = loginLogs.findIndex((l) => l.url === res.url());
      if (idx !== -1) {
        loginLogs[idx].status = res.status();
      }
    });

    // Fill credentials
    await page.locator('[data-testid="input-username"]').fill("owner");
    await page.locator('[data-testid="input-password"]').fill("password");
    await page.locator('[data-testid="btn-login"]').click();

    // Assert successful redirect to dashboard
    await page.waitForURL("http://localhost:3000/");
    expect(page.url()).toBe("http://localhost:3000/");

    // Verify valid session token and user info persist in localStorage
    const token = await page.evaluate(() => localStorage.getItem("portal_session_token"));
    const userRaw = await page.evaluate(() => localStorage.getItem("portal_user"));

    expect(token).not.toBeNull();
    expect(token).toContain("mock_session_token");
    expect(token).toContain("owner");

    expect(userRaw).not.toBeNull();
    const user = JSON.parse(userRaw!);
    expect(user.username).toBe("owner");
    expect(user.role).toBe("owner");

    // Verify navbar displays logged in user badge
    await expect(page.locator('[data-testid="navbar-user"]')).toBeVisible();
    await expect(page.locator('[data-testid="navbar-user"]')).toContainText("owner");

    // Wait for order table or empty state to render
    await expect(page.locator("table")).toBeVisible({ timeout: 10000 });

    // Screenshot authenticated dashboard
    await page.screenshot({
      path: path.resolve(__dirname, "../../playwright-screenshots/02-dashboard-authenticated.png"),
      fullPage: true,
    });
  });
});
