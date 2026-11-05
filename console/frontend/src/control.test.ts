import { describe, it, expect } from "vitest";
import { velocity, editable, controlStatus } from "./control";
describe("keyboard motion", () => {
  it("combines WASD and cancels opposites", () => {
    expect(velocity(new Set(["w", "a"]))).toEqual([0.1, 0.3]);
    expect(velocity(new Set(["w", "s", "a", "d"]))).toEqual([0, 0]);
  });
  it("release produces zero", () =>
    expect(velocity(new Set())).toEqual([0, 0]));
  it("never treats terminal and editable input as teleop", () => {
    expect(editable("INPUT", false)).toBe(true);
    expect(editable("TEXTAREA", false)).toBe(true);
    expect(editable("DIV", true)).toBe(true);
    expect(editable("CANVAS", false)).toBe(false);
  });
});

describe("control status truthfulness", () => {
  it("offline never claims current ownership", () =>
    expect(controlStatus(false, true, true)).toBe("控制状态离线"));
  it("read only never claims parking or ownership", () =>
    expect(controlStatus(true, false, false)).toBe("只读模式"));
  it("autonomy is not mislabeled as parking", () => {
    expect(controlStatus(true, true, false, "autonomous", true)).toBe("自主探索中");
    expect(controlStatus(true, true, false, "autonomous", false)).toBe("自主探索 · 保护停车");
    expect(controlStatus(true, true, false, "starting")).toBe("正在启动探索");
  });
  it("online manual ownership and held release are distinct", () => {
    expect(controlStatus(true, true, true)).toBe("持有控制权");
    expect(controlStatus(true, true, false)).toBe("停车保持");
  });
});


describe("three speed gears", () => {
  it("uses low, middle and high limits", () => {
    expect(velocity(new Set(["w", "a"]), 0)).toEqual([.03, .09]);
    expect(velocity(new Set(["w", "a"]), 1)).toEqual([.06, .18]);
    expect(velocity(new Set(["w", "a"]), 2)).toEqual([.1, .3]);
  });
  it("respects a lower actual robot limit", () => {
    expect(velocity(new Set(["w"]), 1, [.05, .2])).toEqual([.03, 0]);
  });
});
