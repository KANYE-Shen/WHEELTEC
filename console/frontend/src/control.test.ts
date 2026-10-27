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
  it("online manual ownership and held release are distinct", () => {
    expect(controlStatus(true, true, true)).toBe("持有控制权");
    expect(controlStatus(true, true, false)).toBe("停车保持");
  });
});
