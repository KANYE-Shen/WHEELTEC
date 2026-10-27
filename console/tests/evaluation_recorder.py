"""Evaluation only. Never imported by the adapter, gateway or UI."""
import json
import time
import argparse
from pathlib import Path
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    a, ros = p.parse_known_args()
    if a.output.exists():
        raise SystemExit('Refusing to overwrite evaluation evidence')
    rclpy.init(args=ros)
    node = Node('console_independent_evaluator')
    latest = {'command': [0, 0], 'actuator': [0, 0]}
    last = [0.]
    def velocity(key, m): latest[key] = [m.linear.x, m.angular.z]
    output = a.output.open('x')

    def record():
        output.write(json.dumps({**latest, 'wall': time.time(),
                     'stamp': node.get_clock().now().nanoseconds/1e9})+'\n')
        output.flush()
    subscriptions = [node.create_subscription(Twist, '/cmd_vel', lambda m: velocity('command', m), 10),
                     node.create_subscription(Twist, '/simulation/actuator_cmd_vel', lambda m: velocity('actuator', m), 10)]
    timer = node.create_timer(.05, record)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        output.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
