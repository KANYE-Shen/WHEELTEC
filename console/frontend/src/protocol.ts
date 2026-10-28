export type Pose = {
  x: number;
  y: number;
  yaw: number;
  age: number;
  frame: string;
};
export type Stream = {
  stamp: number | null;
  age: number | null;
  hz: number;
  fresh: boolean;
  receiving?: boolean;
  receive_age?: number | null;
  receive_hz?: number;
};
export type Scan = {
  frame: string;
  angle_min: number;
  angle_increment: number;
  range_min: number;
  range_max: number;
  ranges: (number | null)[];
};
export type Grid = {
  revision: number;
  frame: string;
  width: number;
  height: number;
  resolution: number;
  origin: [number, number, number];
  data: number[];
};
export type Log = {
  id: number;
  stamp: number;
  level: number;
  name: string;
  message: string;
};
export type State = {
  connection?: {
    name: string;
    host: string;
    username: string;
    kind: string;
  } | null;
  kind: "robot" | "simulation";
  clock: number;
  connected: boolean;
  maintenance: boolean;
  streams: Record<string, Stream>;
  scan?: Scan;
  map?: Grid;
  pose: Pose | null;
  laser_pose: Pose | null;
  odom?: { linear: number; angular: number; frame: string };
  logs: Log[];
  camera_error?: string;
  control: {
    mine: boolean;
    ready: boolean;
    reason: string;
    enabled: boolean;
    target: [number, number];
    output: [number, number];
    command_timeout: number;
    heartbeat_timeout: number;
    limits: [number, number];
    watchdog: unknown;
    watchdog_fresh: boolean;
    watchdog_revision: number;
  };
};
export type Profile = {
  name: string;
  kind: "robot" | "simulation";
  host: string;
  port: number;
  username: string;
  fingerprint: string;
  key_file: string;
  adapter_port: number;
  desktop_port: number;
};
