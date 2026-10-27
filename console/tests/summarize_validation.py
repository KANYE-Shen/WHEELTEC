"""Independent evaluation summary; never imported by the running console."""
import argparse
import json
import math
from pathlib import Path

def rows(path):
    invalid = 0
    data = []
    for line in path.read_text().splitlines():
        try: data.append(json.loads(line))
        except ValueError: invalid += 1
    return data, invalid

def main():
    p=argparse.ArgumentParser()
    p.add_argument('run', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    poses,bad_pose=rows(a.run/'native-truth.jsonl')
    commands,bad_command=rows(a.run/'commands.jsonl')
    origin=poses[0]['pose'] if poses else None
    result={'native_samples':len(poses),'native_invalid_rows':bad_pose,'command_samples':len(commands),'command_invalid_rows':bad_command,
      'maximum_displacement_m':max((math.hypot(x['pose'][0]-origin[0],x['pose'][1]-origin[1]) for x in poses),default=None),
      'maximum_yaw_change_rad':max((abs(math.atan2(math.sin(x['pose'][2]-origin[2]),math.cos(x['pose'][2]-origin[2]))) for x in poses),default=None),
      'command_abs_max':[max((abs(x['command'][i]) for x in commands),default=None) for i in [0,1]],
      'actuator_abs_max':[max((abs(x['actuator'][i]) for x in commands),default=None) for i in [0,1]]}
    with a.output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
