import { expect, test } from "@playwright/test";

test("shows an optimistic user message and Thinking before the stream begins", async ({ page }) => {
  let releaseResponse!: () => void;
  const responseGate = new Promise<void>((resolve) => { releaseResponse = resolve; });

  await page.goto("/");
  await page.getByRole("button", { name: "+ New session" }).click();
  await page.route("**/api/sessions/*/messages/stream", async (route) => {
    await responseGate;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        'event: run.started\ndata: {"run_id":"delayed-run","status":"planning"}\n\n',
        'event: status\ndata: {"run_id":"delayed-run","status":"executing"}\n\n',
        'event: message.delta\ndata: {"run_id":"delayed-run","delta":"Delayed streamed answer"}\n\n',
        'event: run.completed\ndata: {"run_id":"delayed-run","status":"completed"}\n\n',
        'event: stream.end\ndata: {"run_id":"delayed-run"}\n\n',
      ].join(""),
    });
  });

  await page.getByRole("textbox", { name: "Message" }).fill("Show my message now");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("Show my message now")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Thinking");

  releaseResponse();
  await expect(page.locator(".status")).toHaveText("Completed");
});

test("creates a session and streams a Mock Provider response", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Knowledge, Skill, and Memory" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Open administration" })).toBeVisible();
  await page.getByRole("button", { name: "+ New session" }).click();
  await expect(page.getByRole("heading", { name: "Ask a data question" })).toBeVisible();
  await page.getByRole("textbox", { name: "Message" }).fill("Hello from Playwright");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Phase 1 chat foundation is running with the Mock Provider/).first()).toBeVisible();
  await expect(page.locator(".status")).toHaveText("Completed");
  await page.getByText(/Trace \(/).click();
  await expect(page.getByText("run.completed")).toBeVisible();
});
