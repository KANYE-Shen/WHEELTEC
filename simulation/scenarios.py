"""Evaluator-only metric scenario geometry and runtime SDF generation.

The JSON is consumed here and by map_metrics, never by SLAM/Nav2/exploration.
Room polygon vertices are counter-clockwise and describe the INNER wall face.
Obstacles are axis-aligned [xmin,ymin,xmax,ymax] metre rectangles.
"""
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from scipy.ndimage import label

DIRECTORY = Path(__file__).resolve().parent/'scenarios'


def scenario_ids():
    return sorted(path.stem for path in DIRECTORY.glob('*.json'))


def load_scenario(name):
    if name not in scenario_ids():
        raise ValueError('Unknown scenario: '+str(name)+'; choose '+', '.join(scenario_ids()))
    scene = json.loads((DIRECTORY/(name+'.json')).read_text(encoding='utf-8-sig'))
    validate_scenario(scene)
    return scene


def segments(scene):
    polygon = np.asarray(scene['room'], dtype=float)
    result = [(a,b) for a,b in zip(polygon,np.roll(polygon,-1,axis=0))]
    for obstacle in scene['obstacles']:
        x0,y0,x1,y1 = obstacle['rect']
        vertices = np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]])
        result.extend(zip(vertices,np.roll(vertices,-1,axis=0)))
    return result


def inside_polygon(points, polygon):
    points = np.asarray(points,dtype=float)
    inside = np.zeros(points.shape[:-1],dtype=bool)
    x,y = points[...,0],points[...,1]
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        if a[1] != b[1]:
            inside ^= ((a[1]>y)!=(b[1]>y)) & (x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])
    return inside


def geometry_at(scene, points):
    """Physical free and exact Euclidean center clearance, independent of map."""
    points = np.asarray(points,dtype=float)
    free = inside_polygon(points,scene['room'])
    for obstacle in scene['obstacles']:
        x0,y0,x1,y1 = obstacle['rect']
        free &= ~((points[...,0]>=x0)&(points[...,0]<=x1)&(points[...,1]>=y0)&(points[...,1]<=y1))
    distance = np.full(points.shape[:-1],np.inf)
    for a,b in segments(scene):
        vector = b-a
        fraction = np.clip(np.sum((points-a)*vector,axis=-1)/np.dot(vector,vector),0,1)
        distance = np.minimum(distance,np.linalg.norm(points-(a+fraction[...,None]*vector),axis=-1))
    return free,np.where(free,distance,-distance)


def raster(scene, resolution=.05, padding=.3):
    polygon = np.asarray(scene['room'])
    lower = np.floor((polygon.min(axis=0)-padding)/resolution)*resolution
    shape = np.ceil((polygon.max(axis=0)+padding-lower)/resolution).astype(int)
    xx,yy = np.meshgrid(lower[0]+(np.arange(shape[0])+.5)*resolution,
                        lower[1]+(np.arange(shape[1])+.5)*resolution)
    points = np.stack([xx,yy],axis=-1)
    free,clearance = geometry_at(scene,points)
    return points,free,clearance,[float(lower[0]),float(lower[1]),0.0]


def reachable_mask(scene, spawn, resolution=.05, radius=.35):
    points,free,clearance,origin = raster(scene,resolution)
    safe = free & (clearance>=radius)
    components,_ = label(safe)  # four connected: no diagonal corner cutting
    col,row = np.floor((np.asarray(spawn[:2])-origin[:2])/resolution).astype(int)
    if not (0<=row<safe.shape[0] and 0<=col<safe.shape[1]) or not safe[row,col]:
        raise ValueError('spawn is not a safe robot center')
    return points,free,safe,components==components[row,col],origin


def validate_scenario(scene):
    polygon = scene['room']
    if len(polygon)<4 or not np.isfinite(np.asarray(polygon,dtype=float)).all():
        raise ValueError('room polygon must contain finite vertices')
    # These compact source scenarios deliberately use orthogonal simple polygons.
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        if (a[0]==b[0]) == (a[1]==b[1]):
            raise ValueError('room polygon edges must be nonzero and orthogonal')
    edges = segments({'room':polygon,'obstacles':[]})
    for i,(a,b) in enumerate(edges):
        for j,(c,d) in enumerate(edges):
            if j<=i+1 or (i==0 and j==len(edges)-1):
                continue
            if np.all(np.maximum(np.minimum(a,b),np.minimum(c,d)) <= np.minimum(np.maximum(a,b),np.maximum(c,d))):
                raise ValueError('room polygon self intersects')
    area = .5*sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1]))
    if not 20<=area<=30:
        raise ValueError('room must be counter-clockwise with area 20 to 30 square metres')
    names = set()
    for obstacle in scene['obstacles']:
        x0,y0,x1,y1 = obstacle['rect']
        if not np.isfinite([x0,y0,x1,y1]).all() or x0>=x1 or y0>=y1:
            raise ValueError('invalid obstacle rectangle')
        # Sample its full edges, including concave room corners, not only corners.
        t = np.linspace(0,1,max(3,int(max(x1-x0,y1-y0)/.025)+1))
        boundary = np.concatenate([np.column_stack([x0+t*(x1-x0),np.full_like(t,y0+1e-7)]),
                                   np.column_stack([x0+t*(x1-x0),np.full_like(t,y1-1e-7)]),
                                   np.column_stack([np.full_like(t,x0+1e-7),y0+t*(y1-y0)]),
                                   np.column_stack([np.full_like(t,x1-1e-7),y0+t*(y1-y0)])])
        boundary[:,0]=np.clip(boundary[:,0],x0+1e-7,x1-1e-7)
        boundary[:,1]=np.clip(boundary[:,1],y0+1e-7,y1-1e-7)
        if not inside_polygon(boundary,polygon).all():
            raise ValueError('obstacle outside room')
        if obstacle['name'] in names:
            raise ValueError('duplicate obstacle name')
        names.add(obstacle['name'])
    for i,a in enumerate(scene['obstacles']):
        for b in scene['obstacles'][i+1:]:
            if min(a['rect'][2],b['rect'][2])>max(a['rect'][0],b['rect'][0]) and min(a['rect'][3],b['rect'][3])>max(a['rect'][1],b['rect'][1]):
                raise ValueError('overlapping obstacle rectangles')
    if not 3<=len(scene['spawns'])<=5:
        raise ValueError('scenario needs 3 to 5 named spawns')
    reference = scene['spawns'][0]['pose']
    points,free,safe,reachable,origin = reachable_mask(scene,reference)
    names = set()
    for spawn in scene['spawns']:
        pose = spawn['pose']
        if len(pose)!=3 or not np.isfinite(pose).all() or geometry_at(scene,[pose[:2]])[1][0]<.35:
            raise ValueError('unsafe spawn '+spawn['name'])
        x,y = np.floor((np.asarray(pose[:2])-origin[:2])/.05).astype(int)
        if not reachable[y,x] or spawn['name'] in names:
            raise ValueError('disconnected or duplicate spawn '+spawn['name'])
        names.add(spawn['name'])
    return {'room_area_m2':area,'reachable_safe_area_m2':float(reachable.sum()*.05**2)}


def generate_world(scene, spawn_index, output, pose_override=None):
    """Generate only into caller-selected runtime data; retain GUI/plugins/robot."""
    validate_scenario(scene)
    if not 0<=spawn_index<len(scene['spawns']):
        raise ValueError('spawn index out of range')
    tree = ET.parse(Path(__file__).resolve().parent/'worlds/room_25m2.sdf')
    world = tree.getroot().find('world')
    for model in list(world.findall('model')):
        if model.get('name')!='floor':
            world.remove(model)
    polygon = np.asarray(scene['room'])
    bounds = polygon.max(axis=0)-polygon.min(axis=0)+1
    center = (polygon.max(axis=0)+polygon.min(axis=0))/2
    floor = world.find("model[@name='floor']")
    floor.find('pose').text = f'{center[0]} {center[1]} -0.05 0 0 0'
    for size in floor.findall('.//size'):
        size.text = f'{bounds[0]} {bounds[1]} 0.1'

    def box(name,x,y,sx,sy,angle,height,color):
        model = ET.SubElement(world,'model',name=name)
        ET.SubElement(model,'static').text='true'
        ET.SubElement(model,'pose').text=f'{x} {y} {height/2} 0 0 {angle}'
        link = ET.SubElement(model,'link',name='link')
        for tag in ('collision','visual'):
            part = ET.SubElement(link,tag,name=tag)
            ET.SubElement(ET.SubElement(ET.SubElement(part,'geometry'),'box'),'size').text=f'{sx} {sy} {height}'
            if tag=='visual':
                material=ET.SubElement(part,'material')
                for channel in ('ambient','diffuse'):
                    ET.SubElement(material,channel).text=color
    for i,(a,b) in enumerate(zip(polygon,np.roll(polygon,-1,axis=0))):
        delta=b-a
        length=float(np.linalg.norm(delta))
        middle=(a+b)/2+np.array([delta[1],-delta[0]])/length*.075
        box('wall_'+str(i),*middle,length,.15,math.atan2(delta[1],delta[0]),1.2,'0.65 0.68 0.72 1')
    for obstacle in scene['obstacles']:
        x0,y0,x1,y1=obstacle['rect']
        box(obstacle['name'],(x0+x1)/2,(y0+y1)/2,x1-x0,y1-y0,0,obstacle.get('height',.7),'0.55 0.3 0.15 1')
    pose=scene['spawns'][spawn_index]['pose'] if pose_override is None else pose_override
    if len(pose)!=3 or not np.isfinite(pose).all() or geometry_at(scene,[pose[:2]])[1][0]<.35:
        raise ValueError('unsafe spawn override')
    x,y,yaw = pose
    world.find('include/pose').text=f'{x} {y} 0 0 0 {yaw}'
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    ET.indent(tree)
    tree.write(output,encoding='utf-8',xml_declaration=True)
    return output
