import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
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
const run = process.env.WHEELTEC_TEST_RUN_ID || "20261027-console-off";
function signal(action: string) {
  execFileSync(
    "wsl",
    [
      "-d",
      "WHEELTEC-Ubuntu-22.04",
      "-u",
      "wheeltec",
      "--cd",
      "/mnt/d/虚拟c盘/WHEELTEC",
      "--",
      "python3",
      "console/tests/simulation_fixture.py",
      action,
      "--run-id",
      run,
    ],
    { timeout: 15000 },
  );
}
for (const kind of ["room", "adapter"]) {
  test(`actual ${kind} stream interruption hides stale video and holds after recovery`, async ({
    page,
  }) => {
    let latest: any = null;
    page.on("websocket", (ws) =>
      ws.on("framereceived", (event) => {
        try {
          const m = JSON.parse(event.payload.toString());
          if (m.type === "state") latest = m.data;
        } catch {}
      }),
    );
    await page.goto("/");
    await page.waitForTimeout(400);
    const r = await page.request.post("/api/v1/connect", {
      data: config,
      headers: { Origin: "http://127.0.0.1:8766" },
    });
    expect(r.ok()).toBeTruthy();
    await expect(page.getByAltText("实时相机画面")).toBeVisible({
      timeout: 15000,
    });
    await expect.poll(() => Boolean(latest?.pose)).toBe(true);
    signal(`pause_${kind}`);
    try {
      await expect(page.getByAltText("实时相机画面")).toHaveCount(0, {
        timeout: 15000,
      });
      await expect(page.locator(".control-readings")).toContainText(
        "过期或缺失",
      );
      if (kind === "room") {
        await expect.poll(() => latest?.streams.scan.fresh).toBe(false);
        expect(latest.pose).toBeNull();
        expect(latest.control.mine).toBe(false);
      } else
        await expect(
          page.getByText("未连接 / 数据通道离线", { exact: true }),
        ).toBeVisible({ timeout: 15000 });
    } finally {
      signal(`resume_${kind}`);
    }
    await expect(page.getByAltText("实时相机画面")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByText("停车保持", { exact: true })).toBeVisible();
    expect(latest.control.output).toEqual([0, 0]);
  });
}
