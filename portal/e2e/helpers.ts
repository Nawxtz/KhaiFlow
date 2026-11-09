import { Page, expect } from "@playwright/test";

// Accounts created for the disposable end-to-end database by e2e/setup_backend.sh.
export const E2E_PASSWORD = "e2e-only-test-password";

export async function loginAs(page: Page, username: "owner" | "staff"): Promise<void> {
  await page.goto("/login");
  await page.locator('[data-testid="input-username"]').fill(username);
  await page.locator('[data-testid="input-password"]').fill(E2E_PASSWORD);
  await page.locator('[data-testid="btn-login"]').click();
  await page.waitForURL("http://localhost:3000/");
  await expect(page.locator('[data-testid="navbar-user"]')).toContainText(username);
}
