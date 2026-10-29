"""Robot command gate. Do not run without the corresponding human gate approval."""
import argparse,json,time
from pathlib import Path
from safety import MotionGate
from preflight import validate

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--gate',type=int,choices=[1,2,3],default=1)
    args,ros_args=parser.parse_known_args(); config=validate(json.loads(args.config.read_text()),required_gate=args.gate)
    import rclpy
    from rclpy.node import Node
    from rclpy.clock import Clock,ClockType
    from rclpy.signals import SignalHandlerOptions
    from geometry_msgs.msg import Twist
    from std_msgs.msg import Empty,Bool,String
    from std_srvs.srv import SetBool
    class Watchdog(Node):
        def __init__(self):
            super().__init__('wheeltec_watchdog'); s=config['safety']
            self.gate=MotionGate(s['command_timeout_s'],s['operator_timeout_s'],s['max_linear_m_s'],s['max_yaw_rad_s'])
            self.output_pub=self.create_publisher(Twist,config['driver_command_topic'],10)
            self.status_pub=self.create_publisher(String,'/safety/status',10)
            self.inputs=[self.create_subscription(Twist,'/safety/collision_cmd_vel',lambda m:self.gate.command((m.linear.x,m.angular.z),time.monotonic()),10),
                self.create_subscription(Empty,'/safety/operator_heartbeat',lambda m:self.gate.heartbeat(time.monotonic()),10),
                self.create_subscription(Bool,'/safety/estop',lambda m:self.gate.emergency(m.data),10)]
            self.arm_service=self.create_service(SetBool,'/safety/arm',self.arm)
            self.steady=Clock(clock_type=ClockType.STEADY_TIME)
            self.timer=self.create_timer(.02,self.tick,clock=self.steady)
        def arm(self,request,response):
            if request.data: response.success=self.gate.arm(time.monotonic())
            else: self.gate.stop('operator_hold'); response.success=True
            response.message=self.gate.reason; return response
        def tick(self):
            v,w=self.gate.output(time.monotonic()); message=Twist(); message.linear.x=v; message.angular.z=w
            self.output_pub.publish(message)
            self.status_pub.publish(String(data=json.dumps({'armed':self.gate.armed,'reason':self.gate.reason})))
    rclpy.init(args=ros_args,signal_handler_options=SignalHandlerOptions.NO); node=Watchdog()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.output_pub.publish(Twist()); node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
if __name__=='__main__': main()
