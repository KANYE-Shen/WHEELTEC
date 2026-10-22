"""Save the live occupancy map, pose graph and user reference direction."""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path.home()/'wheeltec_sim_ws/data/maps'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')/'room')
    parser.add_argument('--reference-yaw', type=float, default=0.0, help='Reference heading in map frame, radians')
    parser.add_argument('--no-latest', action='store_true', help='Do not replace the operator most recent map selection')
    args = parser.parse_args()
    if not math.isfinite(args.reference_yaw):
        parser.error('Reference heading must be finite')
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('ROS_DOMAIN_ID','77')
    os.environ['ROS_LOCALHOST_ONLY'] = '1'
    import rclpy
    from nav2_msgs.srv import SaveMap
    from slam_toolbox.srv import SerializePoseGraph
    rclpy.init()
    node = rclpy.create_node('wheeltec_save_map')
    try:
        def call(kind, name, request):
            client = node.create_client(kind, name)
            if not client.wait_for_service(timeout_sec=15):
                raise RuntimeError('Mapping service unavailable: '+name)
            future = client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=30)
            if not future.done() or future.result() is None:
                raise RuntimeError('Map save timed out: '+name)
            return future.result()
        request = SaveMap.Request()
        request.map_topic = '/map'
        request.map_url = str(output)
        request.image_format = 'pgm'
        request.map_mode = 'trinary'
        request.free_thresh = .25
        request.occupied_thresh = .65
        if not call(SaveMap, '/map_saver/save_map', request).result:
            raise RuntimeError('Occupancy map could not be saved')
        graph = SerializePoseGraph.Request()
        graph.filename = str(output)
        if call(SerializePoseGraph,'/slam_toolbox/serialize_map',graph).result != 0:
            raise RuntimeError('SLAM pose graph could not be saved')
        record = {'map_yaml':str(output)+'.yaml', 'posegraph':str(output),
                  'reference_yaw_rad':args.reference_yaw, 'reference_frame':'map',
                  'reference_definition':'User reference; zero is initial robot forward direction',
                  'saved_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        Path(str(output)+'.metadata.json').write_text(json.dumps(record,indent=2))
        if not args.no_latest:
            latest = Path.home()/'wheeltec_sim_ws/data/maps/latest.json'
            latest.parent.mkdir(parents=True,exist_ok=True)
            temporary = latest.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(record,indent=2))
            temporary.replace(latest)
        print(json.dumps(record,indent=2),flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
