"""Audit retained raw outcomes. Does not edit or replace any run result."""
import hashlib,json
from pathlib import Path
import statistics
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'simulation'))
from check_exploration import source_manifest,shutdown_abnormal,launch_shutdown_abnormal
from regression_batch import wilson
DATA=Path.home()/'wheeltec_sim_ws/data/runs'
OUT=Path(__file__).parent
BATCHES=('20261027-irregular-gazebo-v1','20261027-irregular-gazebo-v2','20261027-irregular-nominal-v1','20261027-irregular-runtime-reproductions-v1')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run_summary(path):
    result=json.loads(path.read_text());explorer=result.get('explorer',{})
    saved=result.get('saved_map_metrics',{})
    log=path.with_name('launch.log')
    text=log.read_text(errors='replace') if log.is_file() else ''
    nested_kill=launch_shutdown_abnormal(text)
    clean_shutdown=not nested_kill and all(not shutdown_abnormal(name,p,explorer) for name,p in result.get('shutdown',{}).items() if p)
    return dict(run=str(path.parent),result_sha256=digest(path),strategy=result.get('viewpoint_strategy'),
        scenario=result['scenario'],seed=result['seed'],realism=result['realism_mode'],
        source=result['source'],parameters=explorer.get('parameters'),
        formal_success=result.get('success') is True,functional_success=result.get('functional_success') is True,
        strict_functional_success=result.get('functional_success') is True and clean_shutdown,
        strict_formal_success=result.get('success') is True and clean_shutdown,
        state=explorer.get('state'),reason=explorer.get('reason'),goals=len(explorer.get('goals',[])),
        elapsed_ros_s=explorer.get('elapsed_ros_seconds'),elapsed_wall_s=result.get('elapsed_wall_seconds'),
        truth_distance_m=result.get('truth_traveled_distance_m'),return_error_m=result.get('gazebo_return_error_m'),
        saved_coverage=saved.get('reachable_coverage'),saved_wall_p95_m=saved.get('observable_contour_symmetric_p95_m'),
        saved_contour_coverage=saved.get('observable_contour_coverage'),live_metrics=result.get('map_metrics'),
        truth_valid=result.get('truth_quality',{}).get('valid') is True,
        overlaps=result.get('trajectory_safety',{}).get('geometric_overlap_samples'),
        acceptance=result.get('acceptance'),failures=result.get('failures',[]),
        latest_preserved=result.get('latest_selector_sha256_before')==result.get('latest_selector_sha256_after'),
        nested_sigkill_detected=nested_kill,
        no_live_group_members=all(not p.get('remaining_live_group_members') for p in result.get('shutdown',{}).values() if p),
        cleanup_complete=not nested_kill and all(not p.get('forced_kill') and not p.get('remaining_live_group_members') for p in result.get('shutdown',{}).values() if p),
        clean_shutdown=clean_shutdown,
        resources=result.get('resource_summary'),bag=result.get('rosbag'))


def cells(rows):
    report=[]
    for scene in sorted({r['scenario'] for r in rows}):
        for strategy in ('centroid','visibility'):
            values=[r for r in rows if r['scenario']==scene and r['strategy']==strategy]
            n=len(values);k=sum(r['functional_success'] for r in values)
            metrics={}
            for key in ('saved_coverage','saved_wall_p95_m','saved_contour_coverage','elapsed_ros_s','truth_distance_m'):
                numbers=[r[key] for r in values if r[key] is not None]
                metrics[key]=dict(count=len(numbers),mean=statistics.mean(numbers) if numbers else None,
                                  minimum=min(numbers) if numbers else None,maximum=max(numbers) if numbers else None)
            report.append(dict(scenario=scene,strategy=strategy,trials=n,functional_successes=k,
                functional_wilson_95=wilson(k,n),
                strict_functional_successes=sum(r['strict_functional_success'] for r in values),
                strict_functional_wilson_95=wilson(sum(r['strict_functional_success'] for r in values),n),
                strict_formal_successes=sum(r['strict_formal_success'] for r in values),formal_successes=sum(r['formal_success'] for r in values),
                internal_completed=sum(r['state'] in ('completed','completed_with_residual_frontiers') for r in values),
                zero_goal_trials=sum(r['goals']==0 for r in values),truth_valid=sum(r['truth_valid'] for r in values),
                latest_preserved=all(r['latest_preserved'] for r in values),clean_shutdown=all(r['clean_shutdown'] for r in values),cleanup_complete=all(r['cleanup_complete'] for r in values),
                all_zero_overlap=all(r['overlaps']==0 for r in values),metrics=metrics))
    return report


def main():
    batches=[]
    for name in BATCHES:
        root=DATA/name
        raw=[run_summary(p) for p in sorted(root.glob('*/result.json'))]
        plan=json.loads((root/'plan.json').read_text())
        batches.append(dict(name=name,plan_sha256=digest(root/'plan.json'),planned_trials=len(plan['plan']),
            recorded_trials=len(raw),cells=cells(raw),rows=raw))
    all_rows=[r for b in batches for r in b['rows']]
    current=source_manifest()
    algorithms=['src/wheeltec_explore/wheeltec_explore/'+x for x in ('frontiers.py','viewpoints.py','defaults.py','node.py')]
    matching=all(all(r['source']['sha256'].get(p)==current['sha256'][p] for p in algorithms) for r in all_rows)
    configs=['simulation/config/'+x+'.yaml' for x in ('realism','slam','nav2','bridge')]
    configs+=['simulation/models/wheeltec_reference/model.sdf','simulation/map_metrics.py']
    config_matching=all(all(r['source']['sha256'].get(p)==current['sha256'][p] for p in configs) for r in all_rows)
    harness='simulation/check_exploration.py'
    harness_matching=all(r['source']['sha256'].get(harness)==current['sha256'][harness] for r in all_rows)
    summaries={}
    for name,batch_name in (('mechanism','20261027-irregular-mechanism-v1'),('replay','20261027-irregular-replay-v1'),('checks','20261027-irregular-checks-v3')):
        p=DATA/batch_name/'summary.json'
        if p.is_file():
            summaries[name]=json.loads(p.read_text());summaries[name]['raw_summary_sha256']=digest(p)
            (OUT/(name+'-summary.json')).write_text(json.dumps(summaries[name],indent=2)+'\n')
    report=dict(batches=batches,total_recorded_trials=len(all_rows),current_source=current,
        frozen_algorithm_hashes_match_all_raw=matching,frozen_config_and_evaluator_hashes_match_all_raw=config_matching,
        runtime_harness_hash_matches_all_raw=harness_matching,
        all_latest_preserved=all(r['latest_preserved'] for r in all_rows),
        all_clean_shutdown=all(r['clean_shutdown'] for r in all_rows),
        all_cleanup_complete=all(r['cleanup_complete'] for r in all_rows),
        all_no_live_group_members=all(r['no_live_group_members'] for r in all_rows),
        interpretation='Raw outcomes are immutable. Strict outcomes additionally reject child SIGKILL from retained launch logs in both arms. Runtime harness was tightened after these runs; algorithm/config/evaluator unchanged. Off outcomes are diagnostic; only strict on successes qualify for admission')
    (OUT/'raw-outcome-index.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(total_recorded_trials=len(all_rows),frozen_algorithm_hashes_match_all_raw=matching,frozen_config_and_evaluator_hashes_match_all_raw=config_matching,
        runtime_harness_hash_matches_all_raw=harness_matching,
        all_latest_preserved=report['all_latest_preserved'],all_clean_shutdown=report['all_clean_shutdown'],all_cleanup_complete=report['all_cleanup_complete'],
        batches=[{k:b[k] for k in ('name','planned_trials','recorded_trials','cells')} for b in batches]),indent=2))

if __name__=='__main__':main()
