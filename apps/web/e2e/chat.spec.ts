import { expect, test } from "@playwright/test";


test("creates a session and streams a Mock Provider response", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "+ New session" }).click();
  await expect(page.getByRole("heading", { name: "Ask a data question" })).toBeVisible();
  await page.getByRole("textbox", { name: "Message" }).fill("Hello from Playwright");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Phase 1 chat foundation is running with the Mock Provider/).first()).toBeVisible();
  await expect(page.locator(".status")).toHaveText("Completed");
  await page.getByText(/Trace \(/).click();
  await expect(page.getByText("run.completed")).toBeVisible();
});
