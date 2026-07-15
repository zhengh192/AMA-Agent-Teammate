import { expect, test } from "@playwright/test";


test("plans, approves, executes, charts, and links evidence", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "+ New session" }).click();
  await page
    .getByRole("textbox", { name: "Message" })
    .fill("Query revenue trend for 2025 from the PostgreSQL sales data source.");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByRole("region", { name: "SQL review" })).toBeVisible();
  await expect(page.locator(".status")).toHaveText("Waiting approval");
  await expect(page.getByText("sales_postgres", { exact: true })).toBeVisible();
  await expect(page.locator(".sql-review code")).toContainText("SELECT");

  await page.getByRole("button", { name: "Approve and execute" }).click();
  await expect(page.locator(".status")).toHaveText("Completed", { timeout: 30_000 });
  await expect(page.getByRole("region", { name: "Analysis results" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download CSV" })).toBeVisible();
  await expect(page.getByText("Evidence-linked conclusions")).toBeVisible();
  await expect(page.locator(".plotly-chart .main-svg").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("table tbody tr")).toHaveCount(12);
});
