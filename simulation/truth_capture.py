"""Evaluation-only Gazebo truth with source timestamps and task quality gates.

The existing Pose_V -> TFMessage bridge loses the message-level timestamp.
An independent worker consumes native Pose_V JSON without changing sensor or
algorithm interfaces. The evaluator drains complete records from its JSONL spool.
"""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


def parse_truth_message(message):
    """Extract reference-model world pose and the Pose_V measurement stamp."""
    stamp=message.get('header',{}).get('stamp')
    if not isinstance(stamp,dict):
        raise ValueError('Pose_V message has no measurement stamp')
    sec=int(stamp.get('sec',0))
    nsec=int(stamp.get('nsec',0))
    if sec<0 or not 0<=nsec<1_000_000_000:
        raise ValueError('Invalid Pose_V measurement stamp')
    for pose in message.get('pose',[]):
        if pose.get('name')!='wheeltec_reference':
            continue
        p=pose.get('position',{})
        q=pose.get('orientation',{})
        x,y=float(p.get('x',0)),float(p.get('y',0))
        qx,qy,qz,qw=(float(q.get(key,0)) for key in ('x','y','z','w'))
        if not all(math.isfinite(value) for value in (x,y,qx,qy,qz,qw)) or qx*qx+qy*qy+qz*qz+qw*qw<1e-12:
            raise ValueError('Invalid reference pose')
        heading=math.atan2(2*(qw*qz+qx*qy),1-2*(qy*qy+qz*qz))
        return {'t':sec+nsec/1e9,'pose':[x,y,heading]}
    return None


def truth_quality(samples,terminal_wall_t,task_start_wall_t=0.0,terminal_sim_t=None,
                  maximum_sim_gap=.2,maximum_wall_gap=.5):
    """Assess only [task start, decision], excluding startup and shutdown.

    `t` is the original Gazebo measurement stamp; `wall_t` is reader arrival
    time relative to evaluator start. Repeated poses with advancing stamps are
    valid stationary measurements; repeated stamps cannot prove new truth.
    """
    limits={'minimum_distinct_measurement_stamps':3,'maximum_sim_gap_s':maximum_sim_gap,
            'maximum_wall_gap_s':maximum_wall_gap,'maximum_terminal_sim_age_s':maximum_sim_gap,
            'maximum_terminal_wall_age_s':maximum_wall_gap,'future_tolerance_s':.1}
    if not all(math.isfinite(value) for value in (terminal_wall_t,task_start_wall_t,maximum_sim_gap,maximum_wall_gap)) or maximum_sim_gap<=0 or maximum_wall_gap<=0 or terminal_wall_t<task_start_wall_t:
        raise ValueError('Invalid truth quality interval or limits')
    if terminal_sim_t is not None and not math.isfinite(terminal_sim_t):
        raise ValueError('Invalid terminal simulation time')
    issues=[]
    task=[]
    for sample in samples:
        try:
            wall=float(sample['wall_t'])
            if not math.isfinite(wall):
                raise ValueError('nonfinite wall time')
            if wall<task_start_wall_t or wall>terminal_wall_t:
                continue
            stamp=float(sample['t'])
            pose=sample['pose']
            if len(pose)!=3 or not all(math.isfinite(value) for value in [stamp,*pose]):
                raise ValueError('nonfinite measurement')
            task.append((stamp,wall))
        except (KeyError,TypeError,ValueError):
            if 'invalid_sample' not in issues:
                issues.append('invalid_sample')
    distinct=len({stamp for stamp,wall in task})
    if distinct<limits['minimum_distinct_measurement_stamps']:
        issues.append('insufficient_distinct_measurement_stamps')
    sim_gaps=[b[0]-a[0] for a,b in zip(task,task[1:])]
    wall_gaps=[b[1]-a[1] for a,b in zip(task,task[1:])]
    if any(gap<0 for gap in sim_gaps):
        issues.append('measurement_time_regressed')
    if any(gap<0 for gap in wall_gaps):
        issues.append('arrival_time_regressed')
    sim_gap=max(sim_gaps,default=None)
    last_wall_age=terminal_wall_t-task[-1][1] if task else None
    last_sim_age=terminal_sim_t-task[-1][0] if task and terminal_sim_t is not None else None
    boundary_gaps=[task[0][1]-task_start_wall_t,last_wall_age] if task else []
    wall_gap=max(wall_gaps+boundary_gaps,default=None)
    if sim_gap is not None and sim_gap>maximum_sim_gap+1e-9:
        issues.append('measurement_gap_exceeded')
    if wall_gap is not None and wall_gap>maximum_wall_gap+1e-9:
        issues.append('arrival_gap_exceeded')
    if last_wall_age is None or last_wall_age>maximum_wall_gap+1e-9:
        issues.append('terminal_measurement_stale_wall')
    if last_sim_age is not None and last_sim_age>maximum_sim_gap+1e-9:
        issues.append('terminal_measurement_stale_sim')
    if last_sim_age is not None and last_sim_age < -limits['future_tolerance_s']:
        issues.append('terminal_measurement_in_future')
    return {'valid':not issues,'issues':issues,'limits':limits,
            'task_start_wall_t':task_start_wall_t,'decision_wall_t':terminal_wall_t,
            'decision_sim_t':terminal_sim_t,'task_samples':len(task),
            'distinct_measurement_stamps':distinct,'maximum_sim_gap_s':sim_gap,
            'maximum_wall_gap_s':wall_gap,'last_truth_wall_age_s':last_wall_age,
            'last_truth_sim_age_s':last_sim_age}


def synchronize_terminal_truth(samples,poll,spin_once,simulation_time,started,
                               task_start_wall_t=0.0,timeout=2.0,monotonic=time.monotonic):
    """Resolve callback ordering without weakening source/arrival quality limits.

    Retry only an otherwise healthy future measurement. A retry must acquire
    three new source stamps arriving after entry, so clock catch-up alone cannot
    revive a truth stream which stopped before the synchronization barrier.
    """
    if not math.isfinite(timeout) or not 0<timeout<=2.0:
        raise ValueError('Terminal synchronization budget must be in (0, 2] seconds')
    def snapshot():
        poll()
        return truth_quality(samples,monotonic()-started,task_start_wall_t,simulation_time())
    quality=snapshot()
    entered=monotonic()
    first_wall=entered-started
    first_index=len(samples)
    first_stamp=samples[-1]['t'] if samples else None
    initial_issues=quality['issues'][:]
    attempted=initial_issues==['terminal_measurement_in_future']
    new_stamps=set()
    success=not attempted
    deadline=entered+timeout
    if attempted:
        while deadline-monotonic()>1e-9:
            spin_once(min(.02,deadline-monotonic()))
            quality=snapshot()
            new_stamps={sample['t'] for sample in samples[first_index:]
                        if sample['wall_t']>=first_wall and sample['t']>first_stamp}
            if quality['valid'] and len(new_stamps)>=3:
                success=True
                break
            if any(issue!='terminal_measurement_in_future' for issue in quality['issues']):
                break
        if not success:
            quality['valid']=False
            quality['issues'].append('terminal_clock_sync_missing_new_truth' if len(new_stamps)<3
                                     else 'terminal_clock_sync_timeout')
    quality['terminal_clock_sync']={'attempted':attempted,'maximum_wait_wall_s':timeout,
        'elapsed_wall_s':monotonic()-entered,'initial_issues':initial_issues,
        'required_new_measurement_stamps':3,'new_distinct_measurement_stamps':len(new_stamps)}
    return quality


class GazeboTruthCapture:
    """Owned independent-GIL worker and incremental complete-line spool reader."""
    topic='/world/wheeltec_room/dynamic_pose/info'

    def __init__(self,partition,started,log_path,sample_period=.02):
        self.started=started
        self.sample_period=sample_period
        self.log_path=Path(log_path)
        self.sample_path=self.log_path.with_name('truth-samples.jsonl')
        self.diagnostics_path=self.log_path.with_name('truth-reader-diagnostics.json')
        self._stream=None
        self._partial=b''
        self._consumer_errors=0
        self.error=None
        self.log=self.log_path.open('w')
        self.command=[sys.executable,str(Path(__file__).with_name('truth_capture_worker.py')),
                      '--partition',partition,'--started',repr(started),
                      '--samples',str(self.sample_path),'--diagnostics',str(self.diagnostics_path),
                      '--sample-period',repr(sample_period)]
        self.process=subprocess.Popen(self.command,stdout=self.log,stderr=subprocess.STDOUT,
                                      start_new_session=True)

    def drain(self):
        if self._stream is None:
            if not self.sample_path.is_file():
                return []
            self._stream=self.sample_path.open('rb')
        result=[]
        while True:
            chunk=self._stream.read(65536)
            if not chunk:
                return result
            lines=(self._partial+chunk).split(b'\n')
            self._partial=lines.pop()
            if len(self._partial)>1024*1024:
                self.error='Oversized incomplete truth spool record'
                self._partial=b''
                self._consumer_errors+=1
            for line in lines:
                try:
                    result.append(json.loads(line))
                except (ValueError,TypeError):
                    self._consumer_errors+=1
                    self.error='Invalid complete truth spool record'

    def diagnostics(self):
        report={'raw_messages':0,'retained_samples':0,'parse_errors':0,
                'missing_reference_messages':0,'queue_dropped_samples':0,'reader_error':None}
        if self.diagnostics_path.is_file():
            try:
                report.update(json.loads(self.diagnostics_path.read_text()))
            except (ValueError,OSError) as exc:
                report['reader_error']='Invalid worker diagnostics: '+repr(exc)
        elif self.process.poll() is not None:
            report['reader_error']='Worker stopped without final diagnostics'
        report['parse_errors']+=self._consumer_errors
        report['reader_error']=self.error or report['reader_error']
        return {'time_source':'Gazebo Pose_V.header.stamp',
                'arrival_time_source':'independent worker monotonic wall clock before parse',
                'topic':self.topic,'sample_period_sim_s':self.sample_period,
                'sampling':'retain first, then source stamp >= period or regressed stamp',
                'transport':'append-only UTF-8 JSONL; flush every complete sample',
                'sample_path':str(self.sample_path),'diagnostics_path':str(self.diagnostics_path),
                'maximum_partial_record_bytes':1024*1024,**report}

    def close(self):
        """Call after stopping this instance's owned worker/native process group."""
        self.drain()  # Validate the spool tail without extending the frozen assessment.
        if self._partial:
            self.error='Worker stopped with an incomplete truth spool record'
        if self._stream is not None:
            self._stream.close()
        self.log.close()