import { describe, expect, it } from "vitest";
import { canvasToWorld, gridCellAt, movedPastClickTolerance } from "./mapGeometry";

describe("map clicks", () => {
  it("inverts pan and zoom in CSS pixels, with positive world Y pointing upward", () => {
    expect(canvasToWorld(230, 85, 400, 200, [10, 5], 20)).toEqual({ x: 1, y: 1 });
  });

  it("honors translated, rotated and half-open grid boundaries", () => {
    const grid = { revision: 3, frame: "map", width: 2, height: 3, resolution: 0.5,
      origin: [2, 3, Math.PI / 2] as [number, number, number], data: [0, -1, 100, 0, 0, 0] };
    expect(gridCellAt(grid, { x: 1.25, y: 3.25 })).toBe(100);
    expect(gridCellAt(grid, { x: 1.75, y: 3.75 })).toBe(-1);
    expect(gridCellAt(grid, { x: 2.1, y: 3.25 })).toBeUndefined();
    expect(gridCellAt(grid, { x: 1.75, y: 4.01 })).toBeUndefined();
  });

  it("ignores small finger or mouse motion but distinguishes a drag", () => {
    expect(movedPastClickTolerance(3, 3)).toBe(false);
    expect(movedPastClickTolerance(4, 4)).toBe(true);
  });
});
