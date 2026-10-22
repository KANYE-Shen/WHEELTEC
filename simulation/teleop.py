"""Low-speed keyboard control for the local simulated robot."""
import os
import sys
import time


class DeadmanCommand:
    """A command expires unless the terminal keeps receiving movement keys."""
    KEYS = {'i': (0.15, 0.0), ',': (-0.15, 0.0),
            'j': (0.0, 0.5), 'l': (0.0, -0.5)}

    def __init__(self, timeout=0.35):
        self.timeout = timeout
        self.deadline = 0.0
        self.current = (0.0, 0.0)

    def feed(self, key, now):
        self.current = self.KEYS.get(key.lower(), (0.0, 0.0))
        self.deadline = now + self.timeout

    def velocity(self, now):
        return self.current if now < self.deadline else (0.0, 0.0)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if not sys.stdin.isatty():
        raise SystemExit('Open this controller in an interactive terminal.')

    import select
    import termios
    import tty
    import rclpy
    from geometry_msgs.msg import Twist
    from rclpy.signals import SignalHandlerOptions

    os.environ['ROS_LOCALHOST_ONLY'] = '1'
    os.environ.setdefault('ROS_DOMAIN_ID', '77')
    settings = termios.tcgetattr(sys.stdin)
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('wheeltec_sim_keyboard')
    publisher = node.create_publisher(Twist, '/cmd_vel', 10)
    command = DeadmanCommand()

    def publish(linear=0.0, angular=0.0):
        message = Twist()
        message.linear.x = linear
        message.angular.z = angular
        publisher.publish(message)

    print('WHEELTEC simulated robot keyboard control', flush=True)
    print('Click this terminal and switch to English input.', flush=True)
    print('i: forward   ,: reverse   j: turn left   l: turn right', flush=True)
    print('k / Space: stop   q / Ctrl+C: stop and exit', flush=True)
    print('Release the key: stop within 0.35 s. Do not use during navigation.', flush=True)
    try:
        tty.setcbreak(sys.stdin.fileno())
        while rclpy.ok():
            readable, _, _ = select.select([sys.stdin], [], [], 0.04)
            if readable:
                key = sys.stdin.read(1)
                command.feed(key, time.monotonic())
                if key.lower() == 'q' or key == '\x03' or key == '':
                    break
            publish(*command.velocity(time.monotonic()))
            rclpy.spin_once(node, timeout_sec=0.0)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if rclpy.ok():
                for _ in range(4):
                    publish()
                    rclpy.spin_once(node, timeout_sec=0.01)
                    time.sleep(0.04)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
    print('\nKeyboard control stopped.', flush=True)


if __name__ == '__main__':
    main()