import { expect, test } from "@playwright/test";

test("keeps governance maintenance in /admin", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Knowledge, Skill, and Memory" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Open administration" })).toBeVisible();

  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "AMA Governance Console" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Knowledge, Skill, and Memory" })).toBeVisible();

  const filename = `governed-metric-${Date.now()}.md`;
  await page.locator('input[type="file"]').setInputFiles({
    name: filename,
    mimeType: "text/markdown",
    buffer: Buffer.from("# Metric catalog\nMetric: Net Revenue = invoiced revenue less refunds\n"),
  });
  await expect(page.getByText(filename)).toBeVisible();

  await page.getByPlaceholder("How is Net Revenue defined?").fill("How is Net Revenue defined?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator(".knowledge-answer .label")).toHaveText("Confirmed");
  await expect(page.locator(".knowledge-answer summary").filter({ hasText: `${filename} v1` })).toBeVisible();
});

test("creates a Skill proposal in Agent and approves it in administration", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "+ New session" }).click();
  await page.getByRole("textbox", { name: "Message" }).fill(
    "When analyzing conversion decline, first check completeness, then Geo, Channel, and Intent contribution."
  );
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/pending in the admin console/)).toBeVisible();
  await expect(page.locator(".status")).toHaveText("Completed");

  await page.goto("/admin");
  const proposal = page.locator(".proposal").filter({ hasText: "conversion-decline-analysis" }).filter({ hasText: "pending_approval" }).first();
  await expect(proposal).toBeVisible();
  await proposal.getByRole("button", { name: "Approve exact diff" }).click();
  await expect(page.locator(".proposal").filter({ hasText: "conversion-decline-analysis" }).filter({ hasText: "active" }).first()).toBeVisible();
});