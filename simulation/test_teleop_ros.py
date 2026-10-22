"""Run the real terminal controller in an isolated ROS domain and check Ctrl+C."""
import os
from pathlib import Path
import pty
import signal
import subprocess
import sys
import time
import unittest


class TerminalStopTests(unittest.TestCase):
    def test_ctrl_c_publishes_stop_before_exit(self):
        os.environ.update(ROS_DOMAIN_ID='178', ROS_LOCALHOST_ONLY='1')
        import rclpy
        from geometry_msgs.msg import Twist
        rclpy.init()
        node = rclpy.create_node('keyboard_exit_check')
        received = []
        subscriber = node.create_subscription(Twist, '/cmd_vel', lambda m: received.append(m.linear.x), 100)
        master, slave = pty.openpty()
        child = subprocess.Popen([sys.executable, str(Path(__file__).with_name('teleop.py'))],
                                 stdin=slave, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True, env=os.environ.copy())
        os.close(slave)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not any(v > 0.1 for v in received):
                os.write(master, b'i')
                rclpy.spin_once(node, timeout_sec=0.04)
            self.assertTrue(any(v > 0.1 for v in received), 'No movement command received in isolated ROS domain')
            received.clear()
            child.send_signal(signal.SIGINT)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and (child.poll() is None or not received):
                rclpy.spin_once(node, timeout_sec=0.04)
            self.assertEqual(child.wait(timeout=2), 0)
            self.assertTrue(received, 'Ctrl+C did not publish a final stop')
            self.assertEqual(received[-1], 0.0)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            os.close(master)
            node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()