import { expect, test } from "@playwright/test";

test("separates Knowledge, Skills, and Memory administration", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Knowledge" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Open administration" })).toBeVisible();

  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Build the Agent's governed capability over time" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Governance sections" })).toBeVisible();

  await page.getByRole("link", { name: "Knowledge", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/knowledge$/);
  await expect(page.getByRole("heading", { name: "Source library" })).toBeVisible();

  const unique = Date.now();
  const metric = `PilotMetric${unique}`;
  const filename = `governed-metric-${unique}.md`;
  await page.locator('input[type="file"]').setInputFiles({
    name: filename,
    mimeType: "text/markdown",
    buffer: Buffer.from(`# Metric catalog\nMetric: ${metric} = invoiced revenue less refunds\n`),
  });
  await expect(page.getByText(filename)).toBeVisible();

  await page.getByPlaceholder("How is Net Revenue defined?").fill(`How is ${metric} defined?`);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator(".knowledge-answer .label")).toHaveText("Confirmed");
  await expect(page.locator(".knowledge-answer summary").filter({ hasText: `${filename} v1` })).toBeVisible();

  await page.getByRole("link", { name: "Skills", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Package contract" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Installed analysis skills" })).toBeVisible();
  await expect(page.getByText("9 packages", { exact: true })).toBeVisible();
  await expect(page.locator(".installed-skill").filter({ hasText: "Metric Query" })).toBeVisible();
  await expect(page.locator(".installed-skill").filter({ hasText: "Data Quality Check" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Taught skill proposals" })).toBeVisible();
  await expect(page.locator(".package-tree code").filter({ hasText: "SKILL.md" })).toBeVisible();

  await page.getByRole("link", { name: "Memory", exact: true }).click();
  await expect(page.getByText("Good Memory")).toBeVisible();
  await expect(page.getByText("Not Memory")).toBeVisible();
});

test("creates a Skill proposal in Agent and approves its package in administration", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "+ New session" }).click();
  await page.getByRole("textbox", { name: "Message" }).fill(
    "When analyzing conversion decline, first check completeness, then Geo, Channel, and Intent contribution."
  );
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/pending in the admin console/)).toBeVisible();
  await expect(page.locator(".status")).toHaveText("Completed");

  await page.goto("/admin/skills");
  const proposal = page.locator(".proposal").filter({ hasText: "conversion-decline-analysis" }).filter({ hasText: "pending_approval" }).first();
  await expect(proposal).toBeVisible();
  await expect(proposal.getByText("SKILL.md", { exact: true })).toBeVisible();
  await expect(proposal.getByText("metadata.yaml", { exact: true })).toBeVisible();
  await proposal.getByRole("button", { name: "Approve exact package" }).click();
  await expect(page.locator(".proposal").filter({ hasText: "conversion-decline-analysis" }).filter({ hasText: "active" }).first()).toBeVisible();
});
