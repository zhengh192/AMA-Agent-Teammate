import { expect, test } from "@playwright/test";


test("uploads Knowledge and approval-gates a taught Skill", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Knowledge, Skill, and Memory" })).toBeVisible();

  const filename = `phase3-metric-${Date.now()}.md`;
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

  const teaching =
    "以后分析 conversion 下降时，先检查数据完整性，再拆 Geo、Channel 和 Intent，计算各维度的变化贡献，同时区分确定原因和推断。";
  await page.getByPlaceholder("Teach a repeatable analysis method…").fill(teaching);
  await page.getByRole("button", { name: "Create proposal" }).click();
  const proposal = page.locator(".proposal").filter({ hasText: "conversion-decline-analysis" }).first();
  await expect(proposal).toContainText("pending_approval");
  await proposal.getByRole("button", { name: "Approve exact diff" }).click();
  await expect(proposal).toContainText("active");
});
