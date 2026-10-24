"""ROS-free normal-session paths and saved-map simulator identity.

Simulation identity is a sibling of the map, never part of SLAM or navigation.
Old maps without this sidecar retain the original simulation world.
"""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path


SCENARIOS = Path(__file__).resolve().parent/'scenarios'


def scenario_hash(name):
    path = SCENARIOS/(str(name)+'.json')
    if path.parent != SCENARIOS or not path.is_file():
        raise ValueError('Unknown simulation scenario: '+str(name))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_session(arguments, data_root):
    options = dict(arg.split(':=',1) for arg in arguments if ':=' in arg)
    mode = options.get('mode','mapping')
    explore = options.get('explore','false').lower() == 'true'
    if explore and (mode != 'mapping' or options.get('navigation','true').lower() != 'true'):
        raise ValueError('Exploration requires mapping mode and navigation:=true')
    scenario = options.get('scenario') or None
    if 'spawn' in options and not scenario:
        raise ValueError('spawn:= requires scenario:=ID')
    spawn = int(options.get('spawn','0'))
    map_path = None
    if mode == 'localization':
        if options.get('map'):
            map_path = Path(options['map']).expanduser().resolve()
        else:
            record = Path(data_root)/'maps/latest.json'
            if not record.is_file():
                raise ValueError('No saved map yet. Run mapping and save the map first.')
            map_path = Path(json.loads(record.read_text())['map_yaml']).expanduser().resolve()
        if not map_path.is_file():
            raise ValueError('The most recently saved map is missing: '+str(map_path))
        sidecar = map_path.with_suffix('.simulation.json')
        if not scenario and sidecar.is_file():
            saved = json.loads(sidecar.read_text())
            if saved.get('version') != 1:
                raise ValueError('Unsupported simulation sidecar version: '+str(sidecar))
            scenario, spawn = saved['scenario'], int(saved['spawn_index'])
            if saved.get('scenario_sha256') != scenario_hash(scenario):
                raise ValueError('Scenario source hash differs from the saved map. Restore the scenario source or explicitly pass scenario:=ID to override: '+str(sidecar))
    if explore and scenario is None:
        scenario = 'baseline'
    metadata = {}
    if scenario:
        checksum = scenario_hash(scenario)
        scene = json.loads((SCENARIOS/(scenario+'.json')).read_text(encoding='utf-8-sig'))
        if not 0 <= spawn < len(scene['spawns']):
            raise ValueError('spawn index out of range')
        metadata = {'id':scenario, 'name':scene['name'], 'spawn_index':spawn,
                    'spawn_name':scene['spawns'][spawn]['name'], 'scenario_sha256':checksum}
    return {'options':options, 'scenario':scenario, 'spawn':spawn, 'map':map_path, 'explore':explore, 'metadata':metadata}


def prepare_exploration(session, data_root, stamp=None):
    data_root = Path(data_root)
    stamp = stamp or datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    name = stamp+'_'+session['scenario']+'_spawn'+str(session['spawn'])
    output = Path(session['options'].get('map_output') or data_root/'maps'/name/'room').expanduser().resolve()
    sidecar = output.with_suffix('.simulation.json')
    if sidecar.exists() or output.with_suffix('.yaml').exists():
        raise FileExistsError('Refusing to overwrite an existing simulation map: '+str(output))
    run = data_root/'runs'/name
    run.mkdir(parents=True, exist_ok=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    identity = {'version':1,'scenario':session['scenario'],'spawn_index':session['spawn'],
                'scenario_sha256':session['metadata']['scenario_sha256']}
    # Exclusive creation: a normal run may never rewrite a historical map identity.
    with sidecar.open('x',encoding='utf-8') as stream:
        json.dump(identity,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    session.update(run_dir=run,map_output=output)
    return session


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)


def process_start_ticks(pid, proc_root=Path('/proc')):
    # The parenthesized command field can itself contain spaces or ')'.
    fields = (Path(proc_root)/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
    if fields[0] in ('Z','X'):
        raise ValueError('Session owner has exited')
    return fields[19]


def registry_path(data_root, domain):
    domain = int(domain)
    if not 0 <= domain <= 232:
        raise ValueError('ROS domain must be between 0 and 232')
    return Path(data_root)/'sessions'/('domain-'+str(domain)+'.json')


def register_session(session, data_root, domain, lock_path, owner_pid=None, proc_root=Path('/proc')):
    owner_pid = os.getpid() if owner_pid is None else int(owner_pid)
    stat = Path(lock_path).stat()
    scenario = session['scenario'] or ('baseline' if not session['options'].get('world') else None)
    simulation = None if scenario is None else {
        'version':1, 'scenario':scenario, 'spawn_index':session['spawn'],
        'scenario_sha256':session['metadata'].get('scenario_sha256') or scenario_hash(scenario)}
    record = {'version':1, 'ros_domain_id':int(domain), 'owner_pid':owner_pid,
              'owner_start_ticks':process_start_ticks(owner_pid,proc_root),
              'lock_device':stat.st_dev, 'lock_inode':stat.st_ino,
              'mode':session['options'].get('mode','mapping'), 'simulation':simulation}
    atomic_json(registry_path(data_root,domain),record)
    return record


def active_session(data_root, domain, lock_path=None, proc_root=Path('/proc')):
    """Return identity only while its original process still owns this domain lock."""
    try:
        record = json.loads(registry_path(data_root,domain).read_text())
        if record.get('version') != 1 or record.get('ros_domain_id') != int(domain):
            return None
        pid = record['owner_pid']
        if process_start_ticks(pid,proc_root) != record['owner_start_ticks']:
            return None
        lock_path = Path(lock_path) if lock_path else Path('/tmp')/('wheeltec-room-'+str(int(domain))+'.lock')
        stat = lock_path.stat()
        if (stat.st_dev,stat.st_ino) != (record['lock_device'],record['lock_inode']):
            return None
        # A living old PID is insufficient: it must own this exact FLOCK inode.
        for line in (Path(proc_root)/'locks').read_text().splitlines():
            fields = line.split()
            if len(fields)<6 or fields[1:4] != ['FLOCK','ADVISORY','WRITE'] or fields[4] != str(pid):
                continue
            major,minor,inode = fields[5].split(':')
            if (int(major,16),int(minor,16),int(inode)) == (os.major(stat.st_dev),os.minor(stat.st_dev),stat.st_ino):
                return record
    except (OSError,ValueError,KeyError,TypeError,IndexError):
        return None
    return None