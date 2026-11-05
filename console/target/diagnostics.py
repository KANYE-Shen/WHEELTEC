"""Fault evidence only; this module neither decides motion nor calls ROS."""
import json
from collections import deque
from pathlib import Path


def tf_failure_context(edges, history, target, source, ros_now, wall_now):
    """Describe the received TF chain without treating receipt as source progress."""
    adjacency={}
    for key in edges:
        a,b=key
        adjacency.setdefault(a,[]).append((b,key))
        adjacency.setdefault(b,[]).append((a,key))
    pending=deque([(target,[])])
    visited={target}
    path=None
    while pending:
        frame,chain=pending.popleft()
        if frame==source:
            path=chain
            break
        for other,key in adjacency.get(frame,[]):
            if other not in visited:
                visited.add(other)
                pending.append((other,chain+[key]))
    result=[]
    for key in path or []:
        received,static=edges[key]
        samples=list(history.get(key,()))
        stamp=samples[-1][1] if samples else None
        result.append(dict(parent=key[0],child=key[1],static=static,
            receipt_age_s=wall_now-received,last_received_source_stamp=stamp,
            source_age_s=ros_now-stamp if stamp is not None and not static else None,
            receipt_interval_s=samples[-1][0]-samples[-2][0] if len(samples)>1 else None,
            source_interval_s=samples[-1][1]-samples[-2][1] if len(samples)>1 else None,
            recent_received_samples=samples))
    return dict(tf_chain_found=path is not None,tf_chain=result)


def write_task_stop(run, details):
    """Called after the existing halt; keep the stop after the log ring wraps."""
    if run is None:
        return
    target=Path(run)/'console-stop.json'
    temporary=target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(details,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(target)
