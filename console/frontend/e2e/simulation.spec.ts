import { expect, test } from "@playwright/test";
import { readdir } from "node:fs/promises";
import path from "node:path";

const fixture = process.env.WHEELTEC_SIM_TEST_DIST;
const url = process.env.WHEELTEC_SIM_TEST_URL ?? (fixture ? "http://simulation.test" : undefined);
test.skip(!url, "Set WHEELTEC_SIM_TEST_DIST or WHEELTEC_SIM_TEST_URL for an isolated frontend.");
test.use({ launchOptions: { executablePath: process.env.WHEELTEC_SIM_TEST_BROWSER } });

test("starts mapping, dispatches one goal, cancels, saves and opens the saved map", async ({ page }) => {
  const map = {
    revision: 42, frame: "map", width: 40, height: 40, resolution: 0.1,
    origin: [-2, -2, 0],
    data: Array.from({ length: 1600 }, (_, index) => {
      const x = index % 40, y = Math.floor(index / 40);
      return x < 2 || x >= 38 || y < 2 || y >= 38 || (x >= 33 && y >= 27 && y < 34) ? 100 : 0;
    }),
  };
  const pose = { x: -0.8, y: -0.5, yaw: 0.5, age: 0, frame: "map" };
  const scan = {
    frame: "laser", angle_min: -Math.PI, angle_increment: Math.PI / 90,
    range_min: 0.1, range_max: 8,
    ranges: Array.from({ length: 180 }, (_, index) => index % 6 ? 1.2 + 0.35 * Math.cos(index / 12) : null),
  };
  const starts: object[] = [];
  const goals: { x: number; y: number; yaw: number; frame: string; run_id: string; map_revision: number }[] = [];
  const unexpected: string[] = [];
  const errors: string[] = [];
  let rejectNext = false;
  let saved = false;
  let state: Record<string, unknown> = {
    phase: "stopped", mode: null, message: "", run_id: null, navigation_ready: false,
    map: null, pose: null, laser_pose: null, scan: null, goal: null,
  };
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("websocket", (ws) => unexpected.push(ws.url()));
  if (fixture) {
    await page.route(url! + "/simulation", (route) =>
      route.fulfill({ path: path.join(fixture, "index.html"), contentType: "text/html" }));
    for (const asset of await readdir(path.join(fixture, "assets"))) {
      await page.route(url! + "/assets/" + asset, (route) =>
        route.fulfill({ path: path.join(fixture, "assets", asset) }));
    }
  }
  await page.route("**/bootstrap", (route) => route.fulfill({ json: {} }));
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    switch (new URL(request.url()).pathname) {
      case "/api/v1/simulation/state":
        return route.fulfill({ json: state });
      case "/api/v1/simulation/maps":
        return route.fulfill({ json: { maps: saved ? [{ id: "saved-1", name: "基准房间地图" }] : [] } });
      case "/api/v1/simulation/start": {
        const payload = request.postDataJSON();
        starts.push(payload);
        state = { ...state, phase: "running", mode: payload.mode, message: "", run_id: "run-" + starts.length,
          navigation_ready: true, map, pose, laser_pose: pose, scan, goal: null };
        return route.fulfill({ json: {} });
      }
      case "/api/v1/simulation/goal": {
        const payload = request.postDataJSON();
        if (rejectNext) {
          rejectNext = false;
          return route.fulfill({ status: 409, json: { detail: { code: "blocked", message: "路径已阻塞" } } });
        }
        goals.push(payload);
        state = { ...state, goal: { x: payload.x, y: payload.y, yaw: payload.yaw, status: "active", message: "" } };
        return route.fulfill({ json: {} });
      }
      case "/api/v1/simulation/cancel":
        state = { ...state, goal: { ...(state.goal as object), status: "canceled", message: "" } };
        return route.fulfill({ json: {} });
      case "/api/v1/simulation/save":
        saved = true;
        return route.fulfill({ json: { id: "saved-1", name: "基准房间地图" } });
      case "/api/v1/simulation/stop":
        state = { ...state, phase: "stopped", mode: null, run_id: null, navigation_ready: false,
          map: null, pose: null, laser_pose: null, scan: null, goal: null };
        return route.fulfill({ json: {} });
      default:
        unexpected.push(request.url());
        return route.abort();
    }
  });

  await page.goto(url! + "/simulation");
  await expect(page.getByRole("heading", { name: "仿真操作台" })).toBeVisible();
  await page.getByLabel("场景").selectOption("l_shape");
  await page.getByLabel("随机种子").fill("12");
  await page.getByLabel("激光测距噪声", { exact: false }).fill("0.015");
  await page.getByRole("button", { name: "启动仿真" }).click();
  await expect(page.getByText("可点选目标")).toBeVisible();
  expect(starts[0]).toEqual({ mode: "mapping", scenario: "l_shape", spawn: 0, seed: 12, lidar_noise_stddev: 0.015 });

  const canvas = page.getByLabel("占据栅格地图与雷达");
  const bounds = (await canvas.boundingBox())!;
  const center = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  await page.mouse.move(center.x + 40, center.y + 35, { steps: 4 });
  await page.mouse.up();
  expect(goals).toHaveLength(0);
  await page.mouse.click(center.x + 40 + 58, center.y + 35 - 58);
  await expect.poll(() => goals.length).toBe(1);
  expect(goals[0]).toMatchObject({ frame: "map", map_revision: 42, run_id: "run-1", yaw: 0 });
  expect(goals[0].x).toBeCloseTo(1, 1);
  expect(goals[0].y).toBeCloseTo(1, 1);
  await page.getByRole("button", { name: "取消目标" }).click();
  await expect(page.getByText("目标已取消", { exact: true })).toBeVisible();
  rejectNext = true;
  await page.mouse.click(center.x + 40 + 18, center.y + 35);
  await expect(page.getByRole("alert")).toContainText("路径已阻塞");
  expect(goals).toHaveLength(1);

  await page.getByRole("button", { name: "保存地图" }).click();
  await expect(page.getByText("已保存地图", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "停止仿真" }).click();
  await page.getByLabel("运行模式").selectOption("localization");
  await expect(page.getByRole("combobox", { name: "已存地图", exact: true })).toHaveValue("saved-1");
  await page.getByRole("button", { name: "启动仿真" }).click();
  await expect(page.getByText("可点选目标")).toBeVisible();
  expect(starts[1]).toEqual({ mode: "localization", map_id: "saved-1", seed: 12, lidar_noise_stddev: 0.015 });
  await canvas.click();
  await expect.poll(() => goals.length).toBe(2);
  expect(goals[1]).toMatchObject({ frame: "map", map_revision: 42, run_id: "run-2" });
  expect(unexpected).toEqual([]);
  expect(errors).toEqual([]);

  await page.screenshot({ path: test.info().outputPath("simulation-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(canvas).toBeVisible();
  await expect(page.getByRole("button", { name: "取消目标" })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: test.info().outputPath("simulation-mobile.png"), fullPage: true });
});
