import type { Stream } from "./protocol";
export function streamReadout(key: string, stream: Stream | undefined, online: boolean, elapsed: number) {
  const camera = key === "camera";
  const receiveAge = stream?.receive_age;
  const age = camera && receiveAge != null ? receiveAge : stream?.age;
  const currentAge = age == null ? null : age + Math.max(0, elapsed);
  const receiving = stream?.receiving ?? stream?.fresh;
  const available = Boolean(online && (camera ? receiving : stream?.fresh) &&
    (!camera || receiveAge == null || (currentAge != null && currentAge <= 1)));
  return {
    available,
    hz: camera ? (stream?.receive_hz ?? stream?.hz ?? 0) : (stream?.hz ?? 0),
    age: currentAge,
    timestampWarning: Boolean(camera && online && receiving && !stream?.fresh),
    status: !available ? "不可用 / 过期" : camera ? "接收中" : "实时",
  };
}
