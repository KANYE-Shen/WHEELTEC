"""Bounded, deterministic viewpoint scoring on observed grids; no scene truth."""
import math


def line_of_sight(a,b,free):
    """Supercover center-to-center ray, including both cells at a corner touch.

    Integer crossing-time comparison avoids floating-point corner leaks. Raw
    known-free cells determine visibility; inflated reachability is the caller's
    separate responsibility. Unknown and out-of-grid cells are never evidence.
    """
    x,y=a; tx,ty=b
    dx,dy=abs(tx-x),abs(ty-y)
    sx=1 if tx>x else -1; sy=1 if ty>y else -1
    ix=iy=0
    if (x,y) not in free: return False
    while ix<dx or iy<dy:
        cross_x=(1+2*ix)*dy
        cross_y=(1+2*iy)*dx
        if cross_x==cross_y:
            if (x+sx,y) not in free or (x,y+sy) not in free: return False
            x+=sx; y+=sy; ix+=1; iy+=1
        elif cross_x<cross_y:
            x+=sx; ix+=1
        else:
            y+=sy; iy+=1
        if (x,y) not in free: return False
    return True


def _spread(items,budget):
    # Stable spatial order and equal-rank sampling; never randomize by hash order.
    if len(items)<=budget: return items
    if budget==1: return [items[0]]
    return [items[i*(len(items)-1)//(budget-1)] for i in range(budget)]


def choose_viewpoint(candidates,cluster,free,distances,resolution,
                     score_distance_offset,distance_score_bias,
                     candidate_budget,frontier_budget):
    """Return ((approach, visible aim, estimated visible cells), diagnostics).

    Geometric shortlist includes the old centroid choice; half the budget samples
    the entire spatially sorted candidate set, allowing non-convex alternatives.
    Only sampled LOS is claimed. Empty sampling remains unexplored and must never
    supply evidence for a completion or a footprint-exclusion classification.
    """
    if candidate_budget<1 or frontier_budget<1: raise ValueError('positive viewpoint budgets required')
    cx=sum(p[0] for p in cluster)/len(cluster)
    cy=sum(p[1] for p in cluster)/len(cluster)
    geometric=lambda p:(math.hypot(p[0]-cx,p[1]-cy)+distance_score_bias*distances[p],p)
    ranked=sorted(candidates,key=geometric)
    local_budget=max(1,candidate_budget//2)
    selected=ranked[:local_budget]
    selected+=_spread(sorted(set(candidates)-set(selected)),candidate_budget-len(selected)) if len(selected)<candidate_budget else []
    # De-duplicate for small sets while preserving the baseline candidate first.
    selected=list(dict.fromkeys(selected))
    samples=_spread(sorted(cluster),frontier_budget)
    diagnostics={'candidate_count':len(candidates),'candidates_evaluated':len(selected),
                 'frontier_cells':len(cluster),'frontier_samples':len(samples),
                 'candidate_budget_exhausted':len(selected)<len(candidates),
                 'frontier_sampled':len(samples)<len(cluster),
                 'visible_sample_count':0,'visibility_is_completion_evidence':False}
    best=None; best_key=None
    for candidate in selected:
        visible=[p for p in samples if line_of_sight(candidate,p,free)]
        if not visible: continue
        estimate=len(cluster)*len(visible)/len(samples)
        gain=estimate/(score_distance_offset+distances[candidate]*resolution)
        key=(-gain,geometric(candidate))
        if best_key is None or key<best_key:
            vx=sum(p[0] for p in visible)/len(visible)
            vy=sum(p[1] for p in visible)/len(visible)
            # Aim at an actually visible cell, not an occluded mean behind a wall.
            aim=min(visible,key=lambda p:(math.hypot(p[0]-vx,p[1]-vy),p))
            best=(candidate,aim,estimate); best_key=key
            diagnostics['visible_sample_count']=len(visible)
    return best,diagnostics
