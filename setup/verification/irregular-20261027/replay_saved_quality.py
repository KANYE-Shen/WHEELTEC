"""Deterministically reproduce saved-map contour failure, without replaying motion."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'simulation'))
from map_metrics import load_saved_grid,score_map
from scenarios import load_scenario
RUN=Path.home()/'wheeltec_sim_ws/data/runs/20261027-irregular-nominal-v1/002_irregular_arc_seed1_visibility'
r=json.loads((RUN/'result.json').read_text())
metrics=score_map(load_scenario(r['scenario']),load_saved_grid(RUN/'map.yaml'),r['map_from_world'],r['spawn']['pose'])
keys=('reachable_coverage','observable_contour_symmetric_p95_m','observable_contour_coverage')
report=dict(run=str(RUN),replayed_metrics={k:metrics[k] for k in keys},original_metrics={k:r['saved_map_metrics'][k] for k in keys},
    reproduced=all(abs(metrics[k]-r['saved_map_metrics'][k])<1e-12 for k in keys),
    thresholds_unchanged=dict(coverage=.95,wall_p95_m=.10,contour_coverage=.95),
    final_live_metrics={k:r['map_metrics'][k] for k in keys},
    interpretation='Saved artifact accuracy failure reproduced; later live map improved after return, causal mechanism unverified')
Path(__file__).with_name('saved-quality-replay.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if not report['reproduced']:raise SystemExit(1)
