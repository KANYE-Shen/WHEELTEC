"""One selected velocity source before the existing smoother/collision/watchdog."""
import time
import argparse
import json
from pathlib import Path
from safety import CommandSelector, StatusCadence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path)
    args, ros_args = parser.parse_known_args()
    safety = json.loads(args.config.read_text())['safety'] if args.config else {}
    limits = (min(.1, safety.get('max_linear_m_s', .1)), min(.3, safety.get('max_yaw_rad_s', .3)))
    import rclpy
    from rclpy.node import Node
    from rclpy.clock import Clock, ClockType
    from geometry_msgs.msg import Twist
    from std_msgs.msg import String, Int8
    from std_srvs.srv import SetBool

    class Selector(Node):
        def __init__(self):
            super().__init__('wheeltec_command_selector')
            self.policy = CommandSelector(.5, *limits)
            self.status_cadence = StatusCadence(.1)
            self.output = self.create_publisher(Twist, '/safety/nav_cmd_vel', 10)
            self.status = self.create_publisher(String, '/safety/selected_source', 10)
            self.sources = [self.create_subscription(Twist, '/safety/'+source+'_cmd_vel',
                lambda m, source=source: self.policy.command(source,
                    (m.linear.x, m.angular.z), time.monotonic()), 10)
                for source in ('manual', 'autonomy')]
            self.gear_subscription = self.create_subscription(Int8, '/safety/gear', self.gear, 10)
            self.mode_subscription = self.create_subscription(String,
                '/safety/command_source', self.select, 10)
            self.autonomy_service = self.create_service(SetBool,
                '/safety/select_autonomy', self.autonomy)
            self.steady = Clock(clock_type=ClockType.STEADY_TIME)
            self.timer = self.create_timer(.02, self.tick, clock=self.steady)

        def gear(self, message):
            if message.data in (0, 1, 2):
                self.policy.set_gear(message.data)

        def select(self, message):
            # This channel can only take over or hold; autonomy needs an explicit service call.
            if message.data in ('manual', 'hold'):
                self.policy.select(message.data)
                self.output.publish(Twist())

        def autonomy(self, request, response):
            self.policy.select('autonomy' if request.data else 'hold')
            self.output.publish(Twist())
            response.success = True
            response.message = self.policy.mode + '; final watchdog still requires explicit arm'
            return response

        def tick(self):
            now = time.monotonic()
            v, w = self.policy.output(now)
            message = Twist(); message.linear.x = v; message.angular.z = w
            self.output.publish(message)
            if self.status_cadence.due(self.policy.mode, now):
                self.status.publish(String(data=self.policy.mode))

    rclpy.init(args=ros_args)
    node = Selector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.output.publish(Twist())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
