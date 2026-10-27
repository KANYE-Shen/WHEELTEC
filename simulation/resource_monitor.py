"""Owned process-group CPU/RSS samples; host reference only, not board performance."""
import json
import os
from pathlib import Path
import time


class ProcessResources:
    def __init__(self, output):
        self.output=Path(output); self.last_tick=0.; self.previous={}; self.summary={}
        self.hz=os.sysconf('SC_CLK_TCK')
    def tick(self, groups, force=False):
        now=time.monotonic()
        if not force and now-self.last_tick<1.: return
        self.last_tick=now; rows=[]
        for path in Path('/proc').iterdir():
            if not path.name.isdecimal(): continue
            try:
                fields=(path/'stat').read_text().rpartition(')')[2].split()
                if int(fields[2]) not in groups: continue
                command=(path/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
                role=next((label for label in ('async_slam_toolbox_node','controller_server','planner_server',
                          'bt_navigator','smoother_server','behavior_server','velocity_smoother')
                          if label in command),None)
                if '/lib/wheeltec_explore/explore' in command: role='wheeltec_explore'
                if role is None: continue
                pid=int(path.name); ticks=int(fields[11])+int(fields[12]); start=fields[19]
                rss=int(fields[21])*os.sysconf('SC_PAGE_SIZE')/1024
                previous=self.previous.get((pid,start)); cpu=None
                if previous and now>previous[0]: cpu=100*(ticks-previous[1])/self.hz/(now-previous[0])
                self.previous[(pid,start)]=(now,ticks)
                row={'pid':pid,'role':role,'wall_monotonic':now,'cpu_percent_one_core_basis':cpu,'rss_kib':rss}
                rows.append(row)
                aggregate=self.summary.setdefault(role,{'peak_rss_kib':0,'peak_cpu_percent_one_core_basis':0,'samples':0})
                aggregate['peak_rss_kib']=max(aggregate['peak_rss_kib'],rss)
                aggregate['peak_cpu_percent_one_core_basis']=max(aggregate['peak_cpu_percent_one_core_basis'],cpu or 0)
                aggregate['samples']+=1
            except (FileNotFoundError,ProcessLookupError,PermissionError,IndexError,ValueError): pass
        if rows:
            with self.output.open('a') as stream:
                for row in rows: stream.write(json.dumps(row)+'\n')
