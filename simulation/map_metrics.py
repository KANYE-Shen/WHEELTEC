"""ROS-independent map accuracy and geometric trajectory evaluation.

Alignment is fixed from the INITIAL measured map pose and simulation spawn.
No fitted translation, rotation or scale is estimated from final map geometry.
Coverage denominator is 4-connected ground-truth robot-center space after a
0.35m clearance erosion. Contour denominator uses ground-truth LOS from that
reachable space, so missed walls do not disappear from the denominator.
"""
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from scipy.ndimage import binary_dilation
from scipy.spatial import cKDTree
from scenarios import geometry_at, reachable_mask, raster, segments, inside_polygon


def initial_alignment(spawn, measured_map_pose):
    angle = measured_map_pose[2]-spawn[2]
    c,s=math.cos(angle),math.sin(angle)
    return [measured_map_pose[0]-c*spawn[0]+s*spawn[1],
            measured_map_pose[1]-s*spawn[0]-c*spawn[1],angle]


def transform_points(points, transform):
    points=np.asarray(points,dtype=float)
    c,s=math.cos(transform[2]),math.sin(transform[2])
    return points @ np.array([[c,s],[-s,c]]) + transform[:2]


def inverse_transform(transform):
    c,s=math.cos(transform[2]),math.sin(transform[2])
    return [-c*transform[0]-s*transform[1],s*transform[0]-c*transform[1],-transform[2]]


def truth_grid(scene, resolution=.05):
    points,free,clearance,origin=raster(scene,resolution)
    height,width=free.shape
    return {'width':width,'height':height,'resolution':resolution,'origin':origin,
            'data':np.where(free,0,100).ravel().tolist()}


def sample_grid(grid, points):
    """Nearest containing OccupancyGrid cell, including metadata origin yaw."""
    if grid['resolution']<=0 or len(grid['data'])!=grid['height']*grid['width']:
        raise ValueError('invalid OccupancyGrid dimensions')
    local=transform_points(points,inverse_transform(grid['origin']))
    indices=np.floor(local/grid['resolution']+1e-9).astype(int)
    valid=(indices[...,0]>=0)&(indices[...,0]<grid['width'])&(indices[...,1]>=0)&(indices[...,1]<grid['height'])
    values=np.full(points.shape[:-1],-1,dtype=int)
    data=np.asarray(grid['data']).reshape(grid['height'],grid['width'])
    values[valid]=data[indices[...,1][valid],indices[...,0][valid]]
    return values


def surface_points(scene,resolution=.05):
    samples=[]
    for a,b in segments(scene):
        count=max(1,int(np.ceil(np.linalg.norm(b-a)/resolution)))
        samples.extend(a+((np.arange(count)+.5)/count)[:,None]*(b-a))
    return np.asarray(samples)


def visible_surfaces(scene, surfaces, origins, max_range=10.0):
    """True if at least one reachable center sees the face without obstruction."""
    edges=segments(scene)
    visible=np.zeros(len(surfaces),dtype=bool)
    for index,target in enumerate(surfaces):
        delta=target-origins
        lengths=np.linalg.norm(delta,axis=1)
        candidates=(lengths<=max_range)&(lengths>1e-6)
        blocked=np.zeros(len(origins),dtype=bool)
        for a,b in edges:
            edge=b-a
            denominator=delta[:,0]*edge[1]-delta[:,1]*edge[0]
            good=np.abs(denominator)>1e-10
            offset=a-origins
            fraction=np.full(len(origins),np.inf)
            along=np.full(len(origins),np.inf)
            fraction[good]=(offset[good,0]*edge[1]-offset[good,1]*edge[0])/denominator[good]
            along[good]=(offset[good,0]*delta[good,1]-offset[good,1]*delta[good,0])/denominator[good]
            blocked |= good&(fraction>1e-7)&(fraction<1-1e-5)&(along>=-1e-9)&(along<=1+1e-9)
        visible[index]=bool(np.any(candidates&~blocked))
    return visible


def score_map(scene, grid, map_from_world, spawn, radius=.35, resolution=.05):
    points,physical,safe,reachable,origin=reachable_mask(scene,spawn,resolution,radius)
    values=sample_grid(grid,transform_points(points,map_from_world))
    free=(values>=0)&(values<=25)
    unknown=values<0
    cell_area=resolution**2
    obstacles=np.zeros(physical.shape,dtype=bool)
    for obstacle in scene['obstacles']:
        x0,y0,x1,y1=obstacle['rect']
        obstacles|=(points[...,0]>=x0)&(points[...,0]<x1)&(points[...,1]>=y0)&(points[...,1]<y1)
    count=int(reachable.sum())
    if count==0:
        raise ValueError('no reachable safe cells')
    result={
        'alignment_map_from_world':list(map_from_world),'alignment_method':'fixed_initial_pose_rigid_no_scale',
        'resolution_m':resolution,'robot_center_clearance_radius_m':radius,
        'reachable_safe_cells':count,'reachable_safe_area_m2':count*cell_area,
        'correct_reachable_free_cells':int((reachable&free).sum()),
        'reachable_coverage':float((reachable&free).sum()/count),
        'reachable_unknown_area_m2':float((reachable&unknown).sum()*cell_area),
        'physical_free_area_m2':float(physical.sum()*cell_area),
        'physical_free_unknown_area_m2':float((physical&unknown).sum()*cell_area),
        'other_physical_free_area_m2':float((physical&~reachable).sum()*cell_area),
        'other_physical_free_unknown_area_m2':float((physical&~reachable&unknown).sum()*cell_area),
        'disconnected_safe_area_m2':float((safe&~reachable).sum()*cell_area),
        'false_free_obstacle_cells':int((obstacles&free).sum()),
        'false_free_obstacle_area_m2':float((obstacles&free).sum()*cell_area),
        'false_free_solid_cells':int((~physical&free).sum()),
        'false_free_solid_area_m2':float((~physical&free).sum()*cell_area),
    }
    surfaces=surface_points(scene,resolution)
    # Every safe center is a possible viewpoint. Decimation to 15cm bounds cost;
    # report this explicitly rather than treating actual observed walls as truth.
    origins=points[reachable][::3]
    observable=visible_surfaces(scene,surfaces,origins)
    truth=surfaces[observable]
    data=np.asarray(grid['data']).reshape(grid['height'],grid['width'])
    occupied=data>=65
    adjacent_free=binary_dilation((data>=0)&(data<=25))
    rows,cols=np.where(occupied&adjacent_free)
    mapped=transform_points(np.column_stack([(cols+.5)*grid['resolution'],(rows+.5)*grid['resolution']]),grid['origin'])
    mapped=transform_points(mapped,inverse_transform(map_from_world))
    if len(mapped):
        nearest=cKDTree(surfaces).query(mapped)[1]
        mapped=mapped[observable[nearest]]
    result.update(observable_contour_points=int(len(truth)),mapped_observable_contour_points=int(len(mapped)),
                  contour_observability='ground_truth_LOS_from_reachable_safe_centers_sampled_every_third_cell',
                  contour_sample_spacing_m=resolution,contour_match_tolerance_m=.10,
                  observable_contour_symmetric_p95_m=None,
                  observable_contour_truth_to_map_p95_m=None,
                  observable_contour_map_to_truth_p95_m=None,
                  contour_symmetric_definition='max_of_directional_p95',
                  observable_contour_coverage=None,
                  observable_contour_missing_fraction=None,
                  excluded_contour_points=int((~observable).sum()))
    if len(truth):
        coverage=0.0
        if len(mapped):
            truth_to_map=cKDTree(mapped).query(truth)[0]
            map_to_truth=cKDTree(truth).query(mapped)[0]
            coverage=float(np.mean(truth_to_map<=.10+1e-9))
            result['observable_contour_truth_to_map_p95_m']=float(np.percentile(truth_to_map,95))
            result['observable_contour_map_to_truth_p95_m']=float(np.percentile(map_to_truth,95))
            result['observable_contour_symmetric_p95_m']=max(
                result['observable_contour_truth_to_map_p95_m'],
                result['observable_contour_map_to_truth_p95_m'])
        result['observable_contour_coverage']=coverage
        result['observable_contour_missing_fraction']=1-coverage
    result['limitations']=['Geometric contour accuracy is evaluated only on ground-truth observable faces; interiors and occluded faces excluded.',
                          'Grid quantization is 0.05m; viewpoints are sampled at every third reachable raster cell.',
                          'Final map accuracy does not measure localization drift at every trajectory time.']
    return result


def load_saved_grid(yaml_path):
    import yaml
    from PIL import Image
    path=Path(yaml_path)
    settings=yaml.safe_load(path.read_text())
    if settings.get('mode','trinary')!='trinary':
        raise ValueError('Only explicitly trinary saved maps are supported')
    image=np.asarray(Image.open(path.parent/settings['image']).convert('L'))[::-1].astype(float)/255
    probability=image if settings.get('negate',0) else 1-image
    values=np.full(image.shape,-1,dtype=int)
    values[probability<settings['free_thresh']]=0
    values[probability>settings['occupied_thresh']]=100
    return {'width':image.shape[1],'height':image.shape[0],'resolution':settings['resolution'],
            'origin':settings['origin'],'data':values.ravel().tolist()}


def reference_footprint():
    """Actual top-down collision projection union from the reference SDF.

Casters lie fully inside the body projection. Wheel cylinders rotate about their
axis; their top-down projection is a rectangle, independent of wheel spin.
"""
    path=Path(__file__).resolve().parent/'models/wheeltec_reference/model.sdf'
    model=ET.parse(path).getroot().find('model')
    rectangles=[]
    for link in model.findall('link'):
        link_pose=[float(v) for v in (link.findtext('pose') or '0 0 0 0 0 0').split()]
        for collision in link.findall('collision'):
            box=collision.find('geometry/box/size')
            cylinder=collision.find('geometry/cylinder')
            if box is not None:
                sx,sy,_=map(float,box.text.split())
            elif cylinder is not None:
                sx=2*float(cylinder.findtext('radius'))
                sy=float(cylinder.findtext('length'))
            elif collision.find('geometry/sphere') is not None:
                continue  # caster projections are contained in the body
            else:
                raise ValueError('Unsupported reference footprint geometry')
            x,y=link_pose[:2]
            rectangles.append(np.array([[x-sx/2,y-sy/2],[x+sx/2,y-sy/2],
                                        [x+sx/2,y+sy/2],[x-sx/2,y+sy/2]]))
    return rectangles


def segment_distance(a,b,c,d):
    def cross(u,v):
        return u[0]*v[1]-u[1]*v[0]
    denominator=cross(b-a,d-c)
    if abs(denominator)>1e-12:
        t=cross(c-a,d-c)/denominator
        u=cross(c-a,b-a)/denominator
        if 0<=t<=1 and 0<=u<=1:
            return 0.0
    def point_distance(p,x,y):
        t=np.clip(np.dot(p-x,y-x)/np.dot(y-x,y-x),0,1)
        return float(np.linalg.norm(p-(x+t*(y-x))))
    return min(point_distance(a,c,d),point_distance(b,c,d),point_distance(c,a,b),point_distance(d,a,b))


def trajectory_safety(scene, poses):
    if not poses:
        return {'contact_measurement':'geometric_projection_only','minimum_clearance_m':None,
                'geometric_overlap_samples':None,'geometric_overlap_events':None,'samples':0}
    expanded=[np.asarray(poses[0][-3:],dtype=float)]
    for pose in poses[1:]:
        current=np.asarray(pose[-3:],dtype=float)
        previous=expanded[-1]
        delta=current-previous
        delta[2]=math.atan2(math.sin(delta[2]),math.cos(delta[2]))
        steps=max(1,int(math.ceil(max(np.linalg.norm(delta[:2]),abs(delta[2])*.27)/.02)))
        expanded.extend(previous+delta*(i/steps) for i in range(1,steps+1))
    footprint=reference_footprint()
    edges=np.asarray(segments(scene))
    edge_start=edges[:,0][None,None,:,:]
    edge_end=edges[:,1][None,None,:,:]
    boundary_vector=edge_end-edge_start
    minimum=float('inf')
    all_collisions=[]
    def cross(a,b):
        return a[...,0]*b[...,1]-a[...,1]*b[...,0]
    def point_distance(point,a,b):
        vector=b-a
        fraction=np.clip(np.sum((point-a)*vector,axis=-1)/np.sum(vector*vector,axis=-1),0,1)
        return np.linalg.norm(point-(a+fraction[...,None]*vector),axis=-1)
    # Vectorize actual footprint edges against static wall/obstacle segments in
    # bounded chunks. A high-rate truth log must not make finalization quadratic.
    for offset in range(0,len(expanded),1000):
        chunk=np.asarray(expanded[offset:offset+1000])
        c,s=np.cos(chunk[:,2]),np.sin(chunk[:,2])
        collisions=np.zeros(len(chunk),dtype=bool)
        for part in footprint:
            polygon=np.empty((len(chunk),len(part),2))
            polygon[...,0]=chunk[:,None,0]+c[:,None]*part[None,:,0]-s[:,None]*part[None,:,1]
            polygon[...,1]=chunk[:,None,1]+s[:,None]*part[None,:,0]+c[:,None]*part[None,:,1]
            free,_=geometry_at(scene,polygon)
            collisions|=~free.all(axis=1)
            for obstacle in scene['obstacles']:
                px,py=obstacle['rect'][:2]
                dx,dy=px-chunk[:,0],py-chunk[:,1]
                lx,ly=c*dx+s*dy,-s*dx+c*dy
                collisions|=(lx>=part[:,0].min())&(lx<=part[:,0].max())&(ly>=part[:,1].min())&(ly<=part[:,1].max())
            a=polygon[:,:,None,:]
            b=np.roll(polygon,-1,axis=1)[:,:,None,:]
            vector=b-a
            denominator=cross(vector,boundary_vector)
            good=np.abs(denominator)>1e-12
            fraction=np.divide(cross(edge_start-a,boundary_vector),denominator,out=np.full_like(denominator,np.inf),where=good)
            along=np.divide(cross(edge_start-a,vector),denominator,out=np.full_like(denominator,np.inf),where=good)
            intersections=good&(fraction>=0)&(fraction<=1)&(along>=0)&(along<=1)
            distances=np.minimum.reduce([point_distance(a,edge_start,edge_end),point_distance(b,edge_start,edge_end),
                                         point_distance(edge_start,a,b),point_distance(edge_end,a,b)])
            distances[intersections]=0
            per_pose=distances.min(axis=(1,2))
            minimum=min(minimum,float(per_pose.min()))
            collisions|=per_pose<=1e-9
        all_collisions.extend(collisions.tolist())
    overlaps=sum(all_collisions)
    events=sum(value and (index==0 or not all_collisions[index-1]) for index,value in enumerate(all_collisions))
    return {'contact_measurement':'geometric_projection_only','minimum_clearance_m':0.0 if overlaps else minimum,
            'geometric_overlap_samples':overlaps,'geometric_overlap_events':events,'samples':len(expanded),
            'interpolation_step_m':.02,'footprint':'union_of_reference_SDF_body_and_two_wheel_projections',
            'limitations':'2D projection against static geometry; no physics contact sensor, dynamic obstacles or vertical separation.'}
