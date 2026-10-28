"""Final descriptive statistics. No filtering/retries; missing data stays null."""
import json,math,statistics
from collections import Counter
from pathlib import Path
root=Path('/mnt/d/虚拟c盘/WHEELTEC/setup/verification/2026-10-28-night')
base=Path('/home/wheeltec/wheeltec_sim_ws/data/runs/20261028-active-scan-ab-v3')
summary=json.loads((base/'summary.json').read_text())
assert summary['complete'] and len(summary['rows'])==40
def stats(values):
 values=[x for x in values if x is not None and math.isfinite(x)]
 return {'n':len(values),'median':statistics.median(values) if values else None,
         'min':min(values) if values else None,'max':max(values) if values else None}
rows=[]
for row in summary['rows']:
 run=Path(row['run_dir']);r=json.loads((run/'result.json').read_text())
 e=r.get('explorer') or {};m=r.get('saved_map_metrics') or {}
 t=json.loads((run/'truth.json').read_text())['trajectory']
 valid=(r.get('truth_quality') or {}).get('valid') is True
 rotation=sum(abs(math.atan2(math.sin(b['pose'][2]-a['pose'][2]),math.cos(b['pose'][2]-a['pose'][2]))) for a,b in zip(t,t[1:])) if valid else None
 rows.append(dict(scenario=row['scenario'],seed=row['seed'],angle=row['angle'],
  strict_success=row['success'],state=e.get('state'),reason=e.get('reason'),
  first_goal=row['first_goal'],first_goal_elapsed_ros_s=row.get('first_goal_elapsed_ros_s'),
  initial_observation_events=e.get('active_scans',[]),
  legal_goal_count=len(e.get('goals',[])),frontier_clusters=e.get('frontier_clusters'),
  known_free_area_m2=e.get('known_free_area_m2'),unreachable_clusters=e.get('unreachable_clusters'),
  map_health=e.get('map_health'),coverage=m.get('reachable_coverage'),
  contour_p95_m=m.get('observable_contour_symmetric_p95_m'),
  contour_coverage=m.get('observable_contour_coverage'),
  elapsed_wall_s=r.get('elapsed_wall_seconds'),elapsed_ros_s=e.get('elapsed_ros_seconds'),
  truth_valid=valid,truth_rotation_rad_evaluator_only=rotation,
  truth_travel_m=r.get('truth_traveled_distance_m'),
  return_error_m=r.get('gazebo_return_error_m'),
  safety=r.get('trajectory_safety'),shutdown=r.get('shutdown'),
  wire_status_messages=len(r.get('status_history') or []),
  bag_status_messages=(r.get('rosbag') or {}).get('topic_message_counts',{}).get('/exploration/status',0),
  latest_preserved=r.get('latest_selector_sha256_before')==r.get('latest_selector_sha256_after'),
  failures=r.get('failures',[]),acceptance=r.get('acceptance',{})))
cells=[]
for c in summary['cells']:
 values=[r for r in rows if r['scenario']==c['scenario'] and r['angle']==c['angle']]
 cells.append(dict(**c,states=dict(Counter(r['state'] for r in values)),
  reasons=dict(Counter(r['reason'] for r in values)),coverage=stats([r['coverage'] for r in values]),
  contour_p95_m=stats([r['contour_p95_m'] for r in values]),
  wall_seconds=stats([r['elapsed_wall_s'] for r in values]),
  ros_seconds=stats([r['elapsed_ros_s'] for r in values]),
  truth_valid_count=sum(r['truth_valid'] for r in values),
  truth_travel_m=stats([r['truth_travel_m'] for r in values]),
  truth_rotation_rad=stats([r['truth_rotation_rad_evaluator_only'] for r in values]),
  return_error_m=stats([r['return_error_m'] for r in values])))
audit=dict(batch=base.name,complete=True,strict_successes=sum(r['strict_success'] for r in rows),
 attempted=len(rows),first_goals=sum(r['first_goal'] for r in rows),cells=cells,rows=rows,
 state_counts=dict(Counter(r['state'] for r in rows)),
 wire_terminal_missing=sum(r['state'] is None for r in rows),
 no_motion_requested=all(not e.get('motion_requested') for r in rows for e in r['initial_observation_events']),
 latest_preserved=all(r['latest_preserved'] for r in rows),
 truth_valid_count=sum(r['truth_valid'] for r in rows))
(root/'final-statistics.json').write_text(json.dumps(audit,indent=2)+'\n')
fmt=lambda x:'未验证' if x is None else f'{x:.3f}'
lines=['# P0最终同种子仿真结果（2026-10-28至29）','',
 '严格结果：'+str(audit['strict_successes'])+'/40；首目标：'+str(audit['first_goals'])+'/40。所有40次保留，未修改门限。','',
 '| 场景 | 角度 | 通过 | Wilson95% | 首目标 | 覆盖率中位数 | 轮廓p95中位数(m) | 有效真值 |',
 '| --- | --- | --- | --- | --- | --- | --- | --- |']
for c in cells:
 lo,hi=c['wilson_95']
 lines.append(f"| {c['scenario']} | {c['angle']:g} | {c['successes']}/{c['trials']} | [{lo:.3f},{hi:.3f}] | {c['first_goal_count']}/{c['trials']} | {fmt(c['coverage']['median'])} | {fmt(c['contour_p95_m']['median'])} | {c['truth_valid_count']}/{c['trials']} |")
lines+=['','终态计数：'+json.dumps(audit['state_counts'],ensure_ascii=False)+'。',
 '保存地图指标缺失保持null，不从更好的帧补齐。逐次数据、耗时、前沿、健康、真值行驶/旋转与安全诊断在final-statistics.json；没有首目标时起步时间为null。没有运动不证明运动后SLAM精度。碰撞仅静态几何投影，不是物理接触传感器。',
 '',
 '原v1为0/40，v2部分为0/17（16完整+1中断，余下23个未执行），observer单次smoke失败也保留。不能删掉它们只引用最终批次；本夜若计入两个smoke，共99次仿真尝试。最终40次与v1同场景/起点/种子/角度，额外修复采集握手和未触发的取消路径，不作为改善探索成功率证据。',
 '',
 '结论：当前未证明算法成功率提高。未知扫掠空间仍使主动扫描无法合法启动；保持默认关闭。不调SLAM、缩小足迹或将未知改为空闲。实车G0未通过，下一步先补齐真实有效FOV/足迹、源时间与odom/TF证据。']
(root/'P0-results.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:v for k,v in audit.items() if k not in ('cells','rows')},indent=2))

