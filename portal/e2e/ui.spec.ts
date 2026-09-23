import { test, expect } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

test.describe("UI/UX: i18n & Themes", () => {
  test.beforeEach(async ({ page }) => {
    // Start with a clean state on login page
    await page.goto("/login");
    await page.evaluate(() => localStorage.clear());
  });

  test("Theme Toggle: light to dark, persistence across reload, and back", async ({ page }) => {
    await page.goto("/login");

    // 1. Initial theme check: html element should NOT have 'dark' class by default
    const initialHtmlClass = await page.locator("html").getAttribute("class");
    expect(initialHtmlClass || "").not.toContain("dark");

    // Capture text before theme toggle
    const themeBtnBefore = await page.locator('[data-testid="theme-switcher"]').textContent();
    console.log("[THEME] Button text before toggle:", themeBtnBefore?.trim());

    // 2. Click Theme Switcher
    await page.locator('[data-testid="theme-switcher"]').click();

    // Assert <html> element now has 'dark' class
    await expect(page.locator("html")).toHaveClass(/dark/);
    const darkHtmlClass = await page.locator("html").getAttribute("class");
    expect(darkHtmlClass).toContain("dark");

    // Check localStorage persistence key
    const storedTheme = await page.evaluate(() => localStorage.getItem("user_prefs_theme"));
    expect(storedTheme).toBe("dark");

    // Capture text after theme toggle
    const themeBtnAfter = await page.locator('[data-testid="theme-switcher"]').textContent();
    console.log("[THEME] Button text after toggle:", themeBtnAfter?.trim());

    // Screenshot dark mode active
    await page.screenshot({
      path: path.resolve(__dirname, "../../playwright-screenshots/03-theme-dark-mode.png"),
      fullPage: true,
    });

    // 3. Reload page and assert dark class persists
    await page.reload();
    await expect(page.locator("html")).toHaveClass(/dark/);
    const reloadedTheme = await page.evaluate(() => localStorage.getItem("user_prefs_theme"));
    expect(reloadedTheme).toBe("dark");

    // 4. Toggle back to light mode
    await page.locator('[data-testid="theme-switcher"]').click();
    const finalHtmlClass = await page.locator("html").getAttribute("class");
    expect(finalHtmlClass || "").not.toContain("dark");
    const lightTheme = await page.evaluate(() => localStorage.getItem("user_prefs_theme"));
    expect(lightTheme).toBe("light");
  });

  test("Language Toggle: default Thai to English, persistence across reload, and DOM snapshot", async ({ page }) => {
    // Authenticate as owner so we can verify navigation and full dashboard DOM
    await page.goto("/login");
    await page.evaluate(() => {
      localStorage.setItem("portal_session_token", "mock_session_token_ui_test");
      localStorage.setItem(
        "portal_user",
        JSON.stringify({ id: "seller_owner", username: "owner", role: "owner" })
      );
      localStorage.removeItem("user_prefs_language");
    });

    await page.goto("/");
    await expect(page.locator("table")).toBeVisible({ timeout: 10000 });

    // 1. Capture exact DOM text BEFORE language toggle (Default Thai 'th')
    const pageTitleTh = await page.locator("h1").textContent();
    const navOrdersTh = await page.locator('[data-testid="nav-link-orders"]').textContent();
    const navInventoryTh = await page.locator('[data-testid="nav-link-inventory"]').textContent();
    const logoutBtnTh = await page.locator('[data-testid="btn-logout"]').textContent();
    const orderColIdTh = await page.locator("thead th").nth(0).textContent();
    const langBtnTh = await page.locator('[data-testid="language-switcher"]').textContent();

    const domSnapshotBefore = {
      locale: "th",
      pageTitle: pageTitleTh?.trim(),
      navOrders: navOrdersTh?.trim(),
      navInventory: navInventoryTh?.trim(),
      logoutBtn: logoutBtnTh?.trim(),
      firstTableHeader: orderColIdTh?.trim(),
      languageButton: langBtnTh?.trim(),
    };

    console.log("[I18N SNAPSHOT BEFORE TOGGLE (TH)]:", JSON.stringify(domSnapshotBefore, null, 2));

    // Assert Thai texts
    expect(pageTitleTh?.trim()).toBe("รายการคำสั่งซื้อ");
    expect(navOrdersTh?.trim()).toBe("คำสั่งซื้อ");
    expect(navInventoryTh?.trim()).toBe("คลังสินค้า");
    expect(orderColIdTh?.trim()).toBe("รหัสคำสั่งซื้อ");

    // 2. Click Language Switcher to switch to English ('en')
    await page.locator('[data-testid="language-switcher"]').click();

    // 3. Capture exact DOM text AFTER language toggle (English 'en')
    await expect(page.locator("h1")).toHaveText("Order Dashboard");

    const pageTitleEn = await page.locator("h1").textContent();
    const navOrdersEn = await page.locator('[data-testid="nav-link-orders"]').textContent();
    const navInventoryEn = await page.locator('[data-testid="nav-link-inventory"]').textContent();
    const logoutBtnEn = await page.locator('[data-testid="btn-logout"]').textContent();
    const orderColIdEn = await page.locator("thead th").nth(0).textContent();
    const langBtnEn = await page.locator('[data-testid="language-switcher"]').textContent();

    const domSnapshotAfter = {
      locale: "en",
      pageTitle: pageTitleEn?.trim(),
      navOrders: navOrdersEn?.trim(),
      navInventory: navInventoryEn?.trim(),
      logoutBtn: logoutBtnEn?.trim(),
      firstTableHeader: orderColIdEn?.trim(),
      languageButton: langBtnEn?.trim(),
    };

    console.log("[I18N SNAPSHOT AFTER TOGGLE (EN)]:", JSON.stringify(domSnapshotAfter, null, 2));

    // Assert English texts
    expect(pageTitleEn?.trim()).toBe("Order Dashboard");
    expect(navOrdersEn?.trim()).toBe("Orders");
    expect(navInventoryEn?.trim()).toBe("Inventory");
    expect(orderColIdEn?.trim()).toBe("Order ID");

    // Verify localStorage persistence
    const storedLocale = await page.evaluate(() => localStorage.getItem("user_prefs_language"));
    expect(storedLocale).toBe("en");

    // Screenshot English mode active
    await page.screenshot({
      path: path.resolve(__dirname, "../../playwright-screenshots/04-language-english-mode.png"),
      fullPage: true,
    });

    // 4. Reload page and assert English persists
    await page.reload();
    await expect(page.locator("table")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("h1")).toHaveText("Order Dashboard");
    await expect(page.locator('[data-testid="nav-link-orders"]')).toHaveText("Orders");

    // Save evidence snapshot to JSON file for report inclusion
    const evidenceDir = path.resolve(__dirname, "../../playwright-report");
    if (!fs.existsSync(evidenceDir)) {
      fs.mkdirSync(evidenceDir, { recursive: true });
    }
    fs.writeFileSync(
      path.join(evidenceDir, "dom_i18n_snapshots.json"),
      JSON.stringify({ before: domSnapshotBefore, after: domSnapshotAfter }, null, 2),
      "utf-8"
    );
  });
});
