"""Read-only ROS 2 sensor/TF sampling on the robot; never publishes motion.

Run on the robot after its normal sensor/base drivers have been started.
A passing interface check is separate from measured chassis and motion tests.
"""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import time


def assess_stream(received, stamps, now, stamp_now, minimum_hz):
    count = len(received)
    rate = (count-1)/(received[-1]-received[0]) if count > 1 and received[-1] > received[0] else None
    age = now-received[-1] if count else None
    stamp_age = stamp_now-stamps[-1] if stamps else None
    backwards = sum(b < a for a,b in zip(stamps,stamps[1:]))
    duplicates = sum(b == a for a,b in zip(stamps,stamps[1:]))
    updates = [arrival for index,arrival in enumerate(received)
               if index == 0 or stamps[index] > stamps[index-1]]
    measurement_rate = ((len(updates)-1)/(updates[-1]-updates[0])
                        if len(updates) > 1 and updates[-1] > updates[0] else None)
    measurement_age = now-updates[-1] if updates else None
    zeros = sum(s <= 0 for s in stamps)
    finite = all(math.isfinite(s) for s in stamps)
    fresh = measurement_age is not None and 0 <= measurement_age <= 1.0
    valid_stamp = finite and stamp_age is not None and -.15 <= stamp_age <= 1.0 and not backwards and not zeros
    return {'messages':count,'wall_hz':rate,'measurement_wall_hz':measurement_rate,'duplicate_stamps':duplicates,'distinct_measurements':len(updates),'minimum_hz':minimum_hz,'receive_age_seconds':age,'measurement_age_seconds':measurement_age,
            'stamp_age_seconds':stamp_age,'backwards_stamps':backwards,'zero_stamps':zeros,
            'passed':bool(len(updates) >= 3 and fresh and valid_stamp and measurement_rate is not None and measurement_rate >= minimum_hz)}


def finite_report(value, invalid_fields, path='report'):
    """Retain malformed ROS values as null so a failed check still has a report."""
    if isinstance(value,float) and not math.isfinite(value):
        invalid_fields.append(path)
        return None
    if isinstance(value,dict):
        return {key:finite_report(item,invalid_fields,path+'.'+str(key)) for key,item in value.items()}
    if isinstance(value,list):
        return [finite_report(item,invalid_fields,path+'['+str(index)+']') for index,item in enumerate(value)]
    return value

def resources():
    result = {'architecture':platform.machine(),'ros_distro':os.environ.get('ROS_DISTRO')}
    mem = Path('/proc/meminfo')
    if mem.is_file():
        values = {line.split(':')[0]:int(line.split()[1]) for line in mem.read_text().splitlines()}
        result.update(memory_total_mib=round(values['MemTotal']/1024),memory_available_mib=round(values['MemAvailable']/1024))
    stat = Path('/proc/stat')
    if stat.is_file():
        ticks = [int(v) for v in stat.read_text().splitlines()[0].split()[1:]]
        result['cpu_ticks'] = [sum(ticks[:8]),ticks[3]+ticks[4]]
    board = Path('/proc/device-tree/model')
    if board.is_file():
        result['board_model'] = board.read_text().rstrip('\0')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=float,default=15)
    parser.add_argument('--scan-topic',default='/scan')
    parser.add_argument('--odom-topic',default='/odom')
    parser.add_argument('--base-frame',default='base_link')
    parser.add_argument('--odom-frame',default='odom')
    parser.add_argument('--scan-min-hz',type=float,default=5)
    parser.add_argument('--odom-min-hz',type=float,default=10)
    parser.add_argument('--simulation',action='store_true',help='Only for validating this checker against simulation')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if not 3 <= args.seconds <= 300 or any(not math.isfinite(v) or v <= 0 for v in (args.scan_min_hz,args.odom_min_hz)):
        parser.error('Use 3–300 seconds and positive minimum frequencies')
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        parser.error('Output already exists; choose a new result filename')
    report = {'version':1,'read_only':True,'simulation':args.simulation,'interface_check_passed':False,
              'deployment_ready':False,'physical_motion_tests':'not_run','output':str(output),
              'manual_checks_required':['measured chassis kinematics and dimensions','laser extrinsics',
                                        'wheel/steering calibration','odometry accuracy','braking distance',
                                        'low-speed supervised navigation and actual RDK load'],
              'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'resources_before':resources()}
    node = None
    received = {'scan':[],'odom':[]}
    stamps = {'scan':[],'odom':[]}
    last = {}
    scan_details = {}
    tf_failures = 0
    interrupted = False
    try:
        import rclpy
        from rclpy.parameter import Parameter
        from rclpy.qos import qos_profile_sensor_data
        from rclpy.time import Time
        from sensor_msgs.msg import LaserScan
        from nav_msgs.msg import Odometry
        from tf2_ros import Buffer, TransformListener, TransformException
        rclpy.init()
        node = rclpy.create_node('wheeltec_readonly_interface_check',
                                parameter_overrides=[Parameter('use_sim_time',value=args.simulation)])
        buffer = Buffer(node=node)
        listener = TransformListener(buffer,node)
        collecting = True
        def receive(kind,message):
            if not collecting:
                return
            received[kind].append(time.monotonic())
            stamps[kind].append(message.header.stamp.sec+message.header.stamp.nanosec*1e-9)
            last[kind] = message
            if kind == 'scan':
                valid = sum(math.isfinite(v) and message.range_min <= v <= message.range_max for v in message.ranges)
                scan_details.update(frame_id=message.header.frame_id,beams=len(message.ranges),valid_beams=valid,
                                    range_min_m=message.range_min,range_max_m=message.range_max,
                                    angle_min_rad=message.angle_min,angle_max_rad=message.angle_max)
        subscriptions = [
            node.create_subscription(LaserScan,args.scan_topic,lambda m:receive('scan',m),qos_profile_sensor_data),
            node.create_subscription(Odometry,args.odom_topic,lambda m:receive('odom',m),qos_profile_sensor_data)]
        begin = time.monotonic()
        last_tf = []
        while time.monotonic()-begin < args.seconds:
            rclpy.spin_once(node,timeout_sec=.05)
        # Freeze the sampled sensor messages. Let TF catch up to that exact last
        # scan instead of chasing newer scans while waiting for odometry.
        collecting = False
        tf_deadline = time.monotonic()+.5
        while 'scan' in last:
            message = last['scan']
            stamp = Time.from_msg(message.header.stamp)
            try:
                chain = []
                for parent,child in [(args.odom_frame,args.base_frame),(args.base_frame,message.header.frame_id)]:
                    transform = buffer.lookup_transform(parent,child,stamp).transform
                    p,q = transform.translation,transform.rotation
                    values = [p.x,p.y,p.z,q.x,q.y,q.z,q.w]
                    if not all(math.isfinite(v) for v in values):
                        raise ValueError('non-finite TF')
                    chain.append({'parent':parent,'child':child,'translation_m':values[:3],'quaternion_xyzw':values[3:]})
                last_tf = chain
                break
            except (TransformException,ValueError):
                tf_failures += 1
                if time.monotonic() >= tf_deadline:
                    break
                rclpy.spin_once(node,timeout_sec=.01)
        now = time.monotonic()
        stamp_now = node.get_clock().now().nanoseconds*1e-9
        report['duration_wall_seconds'] = now-begin
        report['streams'] = {kind:assess_stream(received[kind],stamps[kind],now,stamp_now,minimum)
                             for kind,minimum in [('scan',args.scan_min_hz),('odom',args.odom_min_hz)]}
        for kind,topic in [('scan',args.scan_topic),('odom',args.odom_topic)]:
            report['streams'][kind].update(topic=topic,publishers=node.count_publishers(topic))
        report['scan'] = scan_details
        report['tf_at_last_scan_stamp'] = last_tf
        report['tf_lookup_failed_attempts_at_sample_end'] = tf_failures
        if 'odom' in last:
            odom = last['odom']
            report['odom_frames'] = {'parent':odom.header.frame_id,'child':odom.child_frame_id}
        frames_ok = report.get('odom_frames') == {'parent':args.odom_frame,'child':args.base_frame}
        report['interface_check_passed'] = bool(all(s['passed'] for s in report['streams'].values())
                                                and scan_details.get('valid_beams',0) > 0 and last_tf and frames_ok)
    except KeyboardInterrupt:
        interrupted = True
        report['error'] = 'operator_interrupted'
    except Exception as error:
        report['error'] = str(error)
    finally:
        if node is not None:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        report['resources_after'] = resources()
        before = report['resources_before'].pop('cpu_ticks',None)
        after = report['resources_after'].pop('cpu_ticks',None)
        if before and after and after[0] > before[0]:
            report['host_cpu_busy_percent_during_check'] = round(100*(1-(after[1]-before[1])/(after[0]-before[0])),1)
        invalid_fields = []
        report = finite_report(report,invalid_fields)
        if invalid_fields:
            report['interface_check_passed'] = False
            report['error'] = 'nonfinite_values_received'
            report['invalid_numeric_fields'] = invalid_fields
        output.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False))
    return 130 if interrupted else (0 if report['interface_check_passed'] else 1)


if __name__ == '__main__':
    raise SystemExit(main())
