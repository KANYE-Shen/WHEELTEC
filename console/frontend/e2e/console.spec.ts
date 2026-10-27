import { test, expect, Page } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const config = JSON.parse(
  fs.readFileSync(
    process.env.WHEELTEC_TEST_CONNECTION ||
      path.join(os.tmpdir(), "wheeltec-console-20261027", "connection.json"),
    "utf8",
  ),
);
async function boot(page: Page) {
  await page.goto("/");
  await page.waitForTimeout(400);
  const r = await page.request.post("/api/v1/connect", {
    data: config,
    headers: { Origin: "http://127.0.0.1:8766" },
  });
  expect(r.ok()).toBeTruthy();
  await expect(page.getByText("数据通道在线", { exact: true })).toBeVisible({
    timeout: 15000,
  });
}
async function readings(page: Page) {
  return page.locator(".control-readings").innerText();
}
async function claim(page: Page) {
  await page.getByRole("button", { name: "取得手动控制权" }).click();
  await expect(page.getByText("持有控制权", { exact: true })).toBeVisible();
}
async function zero(page: Page) {
  await expect.poll(() => readings(page)).toContain("输出 0.00 / 0.00");
}
test("real scan/map/camera and canvas rendered", async ({ page }) => {
  await boot(page);
  await expect(page.getByAltText("实时相机画面")).toBeVisible();
  await expect(page.getByText("未自动启动 SLAM")).toHaveCount(0);
  expect(
    await page.locator("canvas").evaluate((c: HTMLCanvasElement) => c.width),
  ).toBeGreaterThan(500);
  await page.getByRole("button", { name: "连接设置" }).click();
  await page.screenshot({
    path: "test-results/live-console.png",
    fullPage: true,
  });
});
test("W reaches permitted nonzero output and release stops", async ({ page }) => {
  await boot(page);
  await claim(page);
  await page.keyboard.down("w");
  await expect.poll(() => readings(page)).toContain("输出 0.10");
  await page.keyboard.up("w");
  await zero(page);
});
test("A turns and space latches stop", async ({ page }) => {
  await boot(page);
  await claim(page);
  await page.keyboard.down("a");
  await expect.poll(() => readings(page)).toContain("输出 0.00 / 0.30");
  await page.keyboard.press("Space");
  await page.keyboard.up("a");
  await zero(page);
  await expect(page.getByText("停车保持", { exact: true })).toBeVisible();
});
test("focus on input releases control; WASD types text", async ({ page }) => {
  await boot(page);
  await claim(page);
  const input = page.getByRole("textbox", { name: "筛选日志" });
  await input.focus();
  await page.keyboard.type("wasd");
  await expect(input).toHaveValue("wasd");
  await expect(page.getByText("停车保持", { exact: true })).toBeVisible();
  await zero(page);
});
test("window blur stops and does not auto resume", async ({ page }) => {
  await boot(page);
  await claim(page);
  await page.keyboard.down("w");
  await page.waitForTimeout(300);
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await page.keyboard.up("w");
  await expect(page.getByText("停车保持", { exact: true })).toBeVisible();
  await zero(page);
});
test("hidden page stops and requires explicit reclaim", async ({ page }) => {
  await boot(page);
  await claim(page);
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.getByText("停车保持", { exact: true })).toBeVisible();
  await zero(page);
});
test("second operator cannot steal control", async ({ page, context }) => {
  await boot(page);
  const second = await context.newPage();
  await second.goto("/");
  await expect(second.getByText("数据通道在线", { exact: true })).toBeVisible();
  await page.bringToFront();
  await claim(page);
  await second.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (b) => b.textContent === "取得手动控制权",
    );
    b?.click();
  });
  await expect(second.getByRole("alert")).toContainText("rejected");
  await expect(page.getByText("持有控制权", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "软件停车" }).click();
  await second.close();
});
test("SSH PTY actually executes command and excludes teleop", async ({
  page,
}) => {
  await boot(page);
  await claim(page);
  await page.getByRole("button", { name: "⌘　SSH 终端" }).click();
  await expect(page.locator(".terminal-panel")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "取得手动控制权" }),
  ).toBeDisabled();
  await page.locator(".xterm-helper-textarea").focus();
  await page.keyboard.type('printf "PTY_VERIFIED_20261027\\n"');
  await page.keyboard.press("Enter");
  await expect(page.locator(".xterm-screen")).toContainText(
    "PTY_VERIFIED_20261027",
    { timeout: 10000 },
  );
  await page.getByRole("button", { name: "关闭终端" }).click();
  await zero(page);
});
test("disconnect stops and reconnect holds", async ({ page }) => {
  await boot(page);
  await claim(page);
  await page.keyboard.down("w");
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: "断开连接", exact: true }).click();
  await page.keyboard.up("w");
  await expect(
    page.getByText("未连接 / 数据通道离线", { exact: true }),
  ).toBeVisible();
  const r = await page.request.post("/api/v1/connect", {
    data: config,
    headers: { Origin: "http://127.0.0.1:8766" },
  });
  expect(r.ok()).toBeTruthy();
  await expect(page.getByText("数据通道在线", { exact: true })).toBeVisible();
  await zero(page);
  await expect(page.getByText("停车保持", { exact: true })).toBeVisible();
});
test("noVNC connects through authenticated SSH desktop proxy", async ({
  page,
}) => {
  await boot(page);
  await page.getByRole("button", { name: "▣　仿真桌面" }).click();
  const frame = page.frameLocator("iframe");
  await expect(frame.locator("canvas")).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(3000);
  await page.screenshot({
    path: "test-results/embedded-desktop.png",
    fullPage: true,
  });
});
