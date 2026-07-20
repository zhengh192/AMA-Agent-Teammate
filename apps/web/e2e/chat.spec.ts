import { expect, test } from "@playwright/test";

test("shows an optimistic user message and Thinking before the stream begins", async ({ page }) => {
  let releaseResponse!: () => void;
  const responseGate = new Promise<void>((resolve) => { releaseResponse = resolve; });

  await page.goto("/");
  await page.getByRole("button", { name: "+ 新对话" }).click();
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
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText("Show my message now")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("我先理解一下");

  releaseResponse();
  await expect(page.locator(".status")).toHaveText("可以继续聊");
});

test("creates a session and streams a Mock Provider response", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Knowledge, Skill, and Memory" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "打开后台" })).toBeVisible();
  await page.getByRole("button", { name: "+ 新对话" }).click();
  await expect(page.getByRole("heading", { name: "想看什么，直接问我" })).toBeVisible();
  await page.getByRole("textbox", { name: "Message" }).fill("Hello from Playwright");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText(/我结合前面的对话/).first()).toBeVisible();
  await expect(page.locator(".status")).toHaveText("可以继续聊");
  await page.getByText(/查看审计记录（/).click();
  await expect(page.getByText("run.completed")).toBeVisible();
});


test("keeps the page and composer fixed while only the middle content scrolls", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");

  await page.locator(".conversation").evaluate((conversation) => {
    for (let index = 0; index < 40; index += 1) {
      const message = document.createElement("article");
      message.className = "message assistant";
      message.textContent = `Scrollable test message ${index + 1}`;
      conversation.append(message);
    }
  });

  const scroller = page.locator(".workspace-scroll");
  const composer = page.locator(".composer");
  const before = await composer.boundingBox();
  const initialLayout = await page.evaluate(() => {
    const scrollRegion = document.querySelector<HTMLElement>(".workspace-scroll");
    const shell = document.querySelector<HTMLElement>(".app-shell");
    return {
      viewportHeight: window.innerHeight,
      documentHeight: document.documentElement.scrollHeight,
      bodyScrollY: window.scrollY,
      shellPosition: shell ? getComputedStyle(shell).position : "",
      overflowY: scrollRegion ? getComputedStyle(scrollRegion).overflowY : "",
      scrollHeight: scrollRegion?.scrollHeight ?? 0,
      clientHeight: scrollRegion?.clientHeight ?? 0,
    };
  });

  expect(initialLayout.shellPosition).toBe("fixed");
  expect(initialLayout.documentHeight).toBeLessThanOrEqual(initialLayout.viewportHeight);
  expect(initialLayout.bodyScrollY).toBe(0);
  expect(initialLayout.overflowY).toBe("auto");
  expect(initialLayout.scrollHeight).toBeGreaterThan(initialLayout.clientHeight);

  await scroller.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  const after = await composer.boundingBox();
  const scrollTop = await scroller.evaluate((element) => element.scrollTop);

  expect(scrollTop).toBeGreaterThan(0);
  expect(before).not.toBeNull();
  expect(after).not.toBeNull();
  expect(Math.abs((after?.y ?? 0) - (before?.y ?? 0))).toBeLessThan(1);
  expect((after?.y ?? 0) + (after?.height ?? 0)).toBeLessThanOrEqual(720);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});
