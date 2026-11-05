"""Check the actual adapter subscription wiring without starting ROS/control."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

REPO = Path(__file__).resolve().parents[2]
if not (REPO/'console/target/adapter.py').exists():
    REPO = Path('D:/虚拟c盘/WHEELTEC')


def adapter_wiring():
    tree = ast.parse((REPO/'console/target/adapter.py').read_text(encoding='utf-8'))
    adapter = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == 'Adapter')
    init = next(n for n in adapter.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    assignments = {}
    for n in ast.walk(init):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == 'self':
                    assignments[t.attr] = n
    calls = {}
    node = NS(tf=object(), scan=lambda m:None, map=lambda m:None, odom=lambda m:None,
              camera=lambda m:None, compressed=lambda m:None, log=lambda m:None,
              safety=lambda m:None, selected=lambda m:None)
    node.create_subscription = lambda kind,topic,callback,qos: calls.setdefault(topic, qos)
    def listener(buffer, owner, **kwargs):
        calls['listener'] = kwargs
    env = dict(self=node, args=NS(scan_topic='/scan', map_topic='/map', odom_topic='/odom', camera_topic='/image_raw'),
               TransformListener=listener, QoSProfile=lambda **kwargs:NS(**kwargs),
               DurabilityPolicy=NS(TRANSIENT_LOCAL='transient', VOLATILE='volatile'),
               ReliabilityPolicy=NS(RELIABLE='reliable'), qos_profile_sensor_data=NS(depth=5))
    env.update({name:object() for name in ('LaserScan','OccupancyGrid','Odometry','Image','CompressedImage','Log','String')})
    for name in ('listener', 'subs', 'selection_sub'):
        exec(compile(ast.Module(body=[assignments[name]], type_ignores=[]), 'actual_adapter_wiring', 'exec'), env)
    return calls


class LiveStateQosTests(unittest.TestCase):
    def test_dynamic_tf_has_short_queue_without_changing_static_history(self):
        call = adapter_wiring()['listener']
        self.assertIn('qos', call, 'default TF queue retains 100 old messages during startup stalls')
        self.assertEqual(call['qos'].depth, 10)
        self.assertEqual(call['qos'].durability, 'volatile')
        self.assertEqual(call['qos'].reliability, 'reliable')
        self.assertNotIn('static_qos', call, 'static TF must retain its latched history')

    def test_watchdog_and_selector_consume_latest_state_not_backlog(self):
        calls = adapter_wiring()
        self.assertEqual(calls['/safety/status'], 1)
        self.assertEqual(calls['/safety/selected_source'], 1)


if __name__ == '__main__':
    unittest.main()
