"""Owned evaluation worker: stamp native truth independently of the ROS process GIL."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from truth_capture import parse_truth_message


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partition',required=True)
    parser.add_argument('--started',required=True,type=float)
    parser.add_argument('--samples',required=True,type=Path)
    parser.add_argument('--diagnostics',required=True,type=Path)
    parser.add_argument('--sample-period',required=True,type=float)
    args=parser.parse_args(argv)
    counts={'raw_messages':0,'retained_samples':0,'parse_errors':0,
            'missing_reference_messages':0,'queue_dropped_samples':0}
    stopping=False
    native=None
    error=None
    spool_bytes=0
    maximum_spool_bytes=128*1024*1024
    def stop(*unused):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGINT,stop)
    signal.signal(signal.SIGTERM,stop)
    command=['ign','topic','-e','--json-output','-t','/world/wheeltec_room/dynamic_pose/info']
    try:
        # Same owned process group as this worker, so shutdown reaches both.
        native=subprocess.Popen(command,env=dict(os.environ,IGN_PARTITION=args.partition),
                                stdout=subprocess.PIPE,stderr=sys.stderr,text=True,encoding='utf-8',bufsize=1)
        last_stamp=None
        with args.samples.open('xb') as spool:
            for line in native.stdout:
                # Arrival is captured before parsing and outside the evaluator GIL.
                arrival=time.monotonic()-args.started
                try:
                    message=json.loads(line)
                    counts['raw_messages']+=1
                    sample=parse_truth_message(message)
                    if sample is None:
                        counts['missing_reference_messages']+=1
                        continue
                    stamp=sample['t']
                    if last_stamp is not None and last_stamp<=stamp<last_stamp+args.sample_period-1e-9:
                        continue
                    last_stamp=stamp
                    sample['wall_t']=arrival
                    encoded=(json.dumps(sample,separators=(',',':'))+'\n').encode('utf-8')
                    if spool_bytes+len(encoded)>maximum_spool_bytes:
                        counts['queue_dropped_samples']+=1
                        raise RuntimeError('Evaluation truth spool exceeded its explicit byte limit')
                    spool.write(encoded)
                    spool.flush()
                    spool_bytes+=len(encoded)
                    counts['retained_samples']+=1
                except (ValueError,TypeError,KeyError):
                    counts['parse_errors']+=1
        if not stopping:
            error='Native truth reader exited before owned shutdown'
    except Exception as exc:
        error=repr(exc)
    finally:
        if native is not None:
            try:
                if native.poll() is None:
                    native.send_signal(signal.SIGINT)
                native.wait(timeout=5)
            except subprocess.TimeoutExpired:
                native.kill()
                native.wait(timeout=2)
                error=error or 'Native truth reader required forced shutdown'
            if native.stdout is not None:
                native.stdout.close()
        report={**counts,'reader_error':error,'native_returncode':native.returncode if native is not None else None,
                'worker_pid':os.getpid(),'native_pid':native.pid if native is not None else None,
                'spool_bytes':spool_bytes,'maximum_spool_bytes':maximum_spool_bytes}
        temporary=args.diagnostics.with_suffix(args.diagnostics.suffix+'.tmp')
        temporary.write_text(json.dumps(report,separators=(',',':'))+'\n')
        os.replace(temporary,args.diagnostics)
    return 1 if error else 0


if __name__=='__main__':
    raise SystemExit(main())