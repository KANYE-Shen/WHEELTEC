import { describe, it, expect } from "vitest";
import { streamReadout } from "./streamReadout";
describe("camera receive frequency", () => {
 it("keeps the Hz readout when capture timestamps jump into the future", () => {
  const a = streamReadout("camera",{stamp:10.8,age:-.8,hz:17,fresh:false,receiving:true,receive_age:.1,receive_hz:7.5},true,.1);
  expect(a.available).toBe(true);expect(a.hz).toBe(7.5);expect(a.age).toBeCloseTo(.2);expect(a.timestampWarning).toBe(true);
 });
 it("hides stale or disconnected camera readings", () => {
  const s={stamp:10,age:0,hz:7.5,fresh:true,receiving:true,receive_age:.8,receive_hz:7.5};
  expect(streamReadout("camera",s,true,.3).available).toBe(false);
  expect(streamReadout("camera",s,false,0).available).toBe(false);
 });
 it("does not use receive liveness to approve laser measurements", () => {
  expect(streamReadout("scan",{stamp:10.8,age:-.8,hz:10,fresh:false,receiving:true},true,0).available).toBe(false);
 });
 it("supports older adapters without receive metadata", () => {
  expect(streamReadout("camera",{stamp:10,age:.1,hz:8,fresh:true},true,0).hz).toBe(8);
  expect(streamReadout("camera",undefined,true,0).available).toBe(false);
 });
});
