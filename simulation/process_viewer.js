/* Estimate-only replay logic, shared by offline HTML, live HTML and Node tests. */
(function (root) {
  'use strict';
  const finite = Number.isFinite;
  const point = p => Array.isArray(p) && p.length >= 2 && finite(p[0]) && finite(p[1]);
  function snapshot(document, index) {
    const frames = document.frames || [], maps = document.maps || [];
    const end = Math.max(0, Math.min(Math.trunc(index), frames.length - 1));
    const frame = frames[end] || null;
    if (!frame) return {frame:null, map:null, segments:[], reference:null, relativeAngle:null, status:{}, distance:0};
    const segments = []; let segment = [], firstPose = null, distance = 0;
    for (let i = 0; i <= end; i++) {
      const pose = frames[i].pose;
      if (point(pose) && finite(pose[2])) {
        if (!firstPose) firstPose = pose;
        const previous = segment[segment.length-1];
        if (previous) distance += Math.hypot(pose[0]-previous[0], pose[1]-previous[1]);
        segment.push(pose.slice(0,2));
      } else if (segment.length) {
        segments.push(segment); segment = [];
      }
    }
    if (segment.length) segments.push(segment);
    const initial = document.capture && document.capture.initial_pose;
    const reference = firstPose ? (point(initial) && finite(initial[2]) &&
      document.capture.initial_pose_t <= frame.t ? initial[2] : firstPose[2]) : null;
    const relativeAngle = point(frame.pose) && finite(frame.pose[2]) && reference !== null ?
      Math.atan2(Math.sin(frame.pose[2]-reference), Math.cos(frame.pose[2]-reference))*180/Math.PI : null;
    const map = Number.isInteger(frame.map) && frame.map >= 0 ? maps[frame.map] || null : null;
    const status = frame.status && Object.keys(frame.status).length ? frame.status :
      (end === frames.length-1 && document.terminal ? document.terminal : {});
    return {frame, map, segments, reference, relativeAngle, status, distance};
  }
  function freshness(now, lastAdvance, error) {
    return error ? 'disconnected' : (now-lastAdvance > 12000 ? 'stalled' : 'receiving');
  }
  const api = {snapshot, freshness};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.WheeltecReplay = api;
  if (typeof document === 'undefined') return;

  const $ = id => document.getElementById(id);
  const text = (id, value) => { $(id).textContent = value; };
  const read = id => JSON.parse($(id).textContent);
  let data = read('process-data') || {frames:[],maps:[]};
  let result = read('result-data'), live = read('live-data'), index = live ? Math.max(0,data.frames.length-1) : 0;
  let follow = live, playing = false, lastTick = null, playTime = 0;
  let lastAdvance = performance.now(), lastFetchError = false, signature = '';
  let view = null, gridKey = null, gridCanvas = null;
  const canvas = $('map'), ctx = canvas.getContext('2d');
  const layers = {grid:true,scan:true,pose:true,trail:true,plan:true};
  const states = {starting:'准备中', exploring:'正在探索', saving:'正在保存地图', returning:'正在返回起点',
    completed:'任务完成', completed_with_residual_frontiers:'完成（有已分类残余）', map_unstable:'地图不稳定', incomplete:'任务未完成', failed:'任务失败', interrupted:'人工中止'};
  const reasons = {no_reachable_frontiers:'未再发现可达前沿', operator_interrupted:'操作员在终端中止',
    unresolved_frontiers:'还有未解决的探索区域', return_to_start_failed:'返回起点失败',
    task_timeout:'达到本次任务时限', max_goals:'达到目标数量限制'};
  const issues = {missing_map_transform:'缺少 map → base_link 变换', stale_pose_transform:'位置变换已过期，暂不显示车位',
    missing_scan:'尚未收到激光', stale_scan:'激光已过期，暂不绘制', missing_scan_transform:'激光坐标变换不可用',
    missing_plan_transform:'规划路线坐标变换不可用'};
  function number(value, digits=2, unit='') { return finite(value) ? value.toFixed(digits)+unit : '—'; }
  function assessment() {
    if (!result) {
      text('assessment','未评分'); $('assessment').className='state';
      text('assessment-note','普通探索记录没有独立真值评分。任务完成与地图验收分别显示。');
    } else if (typeof result.success === 'boolean') {
      text('assessment', result.success ? '通过' : '未通过');
      $('assessment').className='state '+(result.success ? 'good' : 'bad');
      text('assessment-note','本次最终评分，适用于整段运行；与当前回放时刻的任务状态分别显示。');
    } else {
      text('assessment','未评分'); $('assessment').className='state';
      text('assessment-note','当前记录只有任务过程，没有独立地图验收评分。');
    }
    const metric = result && (result.saved_map_metrics || result.map_metrics) || {};
    text('coverage',finite(metric.reachable_coverage) ? (metric.reachable_coverage*100).toFixed(1)+'%' : '—');
    text('p95',number(metric.observable_contour_symmetric_p95_m,3,' m'));
    text('return-error',number(result && result.gazebo_return_error_m,3,' m'));
  }
  function sourceStatus() {
    if (!live) { text('source-status','离线回放 · 页面已包含全部记录，无需服务器'); return; }
    const state = freshness(performance.now(), lastAdvance, lastFetchError);
    const last = data.frames[data.frames.length-1];
    const stamp = last ? '最后记录：模拟 '+number(last.t,1,' s')+' / 录制 '+number(last.wall_t,1,' s') : '等待第一帧';
    const ended = last && last.status && ['completed','completed_with_residual_frontiers','map_unstable','incomplete','failed','interrupted'].includes(last.status.state);
    const label = state==='disconnected' ? '连接已中断，保留最后数据' : ended ? '任务已结束，显示最终记录' :
      state==='stalled' ? '数据未继续，仿真可能已暂停或停止' : '读取中 · 约每 5 秒刷新';
    text('source-status',label+' · '+stamp);
    if (root.WheeltecViewerState) root.WheeltecViewerState.freshness=state;
    $('source-status').className='live-status'+(state==='receiving' ? '' : ' warning');
  }
  function bounds(state) {
    const points = [];
    const map = state.map;
    if (map && layers.grid && finite(map.resolution) && point(map.origin)) {
      const a = map.origin[2] || 0, c=Math.cos(a), s=Math.sin(a);
      for (const [x,y] of [[0,0],[map.width*map.resolution,0],[0,map.height*map.resolution],[map.width*map.resolution,map.height*map.resolution]]) {
        points.push([map.origin[0]+c*x-s*y,map.origin[1]+s*x+c*y]);
      }
    }
    if (state.frame) {
      if (layers.scan) points.push(...(state.frame.scan || []).filter(point));
      if (layers.plan) points.push(...(state.frame.plan || []).filter(point));
      if (point(state.frame.pose)) points.push(state.frame.pose);
    }
    if (layers.trail) for (const segment of state.segments) points.push(...segment);
    if (!points.length) return [-2,-2,2,2];
    let xmin=Infinity,ymin=Infinity,xmax=-Infinity,ymax=-Infinity;
    for (const p of points) { xmin=Math.min(xmin,p[0]); ymin=Math.min(ymin,p[1]); xmax=Math.max(xmax,p[0]); ymax=Math.max(ymax,p[1]); }
    return [xmin-.5,ymin-.5,Math.max(xmax,xmin+.5)+.5,Math.max(ymax,ymin+.5)+.5];
  }
  function line(points,color,width,dashed=false) {
    if (!points || !points.length) return;
    ctx.beginPath(); let begun=false;
    for (const p of points) {
      if (!point(p)) {begun=false;continue;}
      if (!begun) {ctx.moveTo(p[0],p[1]);begun=true;} else ctx.lineTo(p[0],p[1]);
    }
    ctx.strokeStyle=color; ctx.lineWidth=width; ctx.setLineDash(dashed ? [width*4,width*3] : []); ctx.stroke(); ctx.setLineDash([]);
  }
  function draw(state) {
    const rect=canvas.getBoundingClientRect(), ratio=window.devicePixelRatio || 1;
    if (canvas.width!==Math.round(rect.width*ratio) || canvas.height!==Math.round(rect.height*ratio)) {
      canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);
    }
    const width=canvas.width,height=canvas.height;
    ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#e3e8ed';ctx.fillRect(0,0,width,height);
    view=bounds(state);
    const scale=Math.min(width/(view[2]-view[0]),height/(view[3]-view[1]));
    const cx=(view[0]+view[2])/2,cy=(view[1]+view[3])/2;
    ctx.setTransform(scale,0,0,-scale,width/2-cx*scale,height/2+cy*scale);
    const map=state.map;
    if (layers.grid && map && Number.isInteger(map.width) && Number.isInteger(map.height) &&
        map.width>0 && map.height>0 && map.width*map.height<=5000000 &&
        Array.isArray(map.data) && map.data.length===map.width*map.height && finite(map.resolution) && point(map.origin)) {
      if (gridKey!==map) {
        gridCanvas=document.createElement('canvas');gridCanvas.width=map.width;gridCanvas.height=map.height;
        const g=gridCanvas.getContext('2d'),image=g.createImageData(map.width,map.height);
        for (let i=0;i<map.data.length;i++) {
          const value=map.data[i], shade=value<0 ? 173 : Math.round(250-Math.max(0,Math.min(100,value))*2.2);
          image.data[i*4]=shade;image.data[i*4+1]=shade;image.data[i*4+2]=shade;image.data[i*4+3]=255;
        }
        g.putImageData(image,0,0);gridKey=map;
      }
      ctx.save();ctx.translate(map.origin[0],map.origin[1]);ctx.rotate(map.origin[2] || 0);ctx.imageSmoothingEnabled=false;
      ctx.drawImage(gridCanvas,0,0,map.width*map.resolution,map.height*map.resolution);ctx.restore();
    }
    if (layers.trail) for (const segment of state.segments) line(segment,'#b47726',2.4*ratio/scale);
    const frame=state.frame;
    if (frame && layers.plan) line(frame.plan,'#287cbb',2.2*ratio/scale,frame.plan_age_wall_s>5);
    if (frame && layers.scan && Array.isArray(frame.scan)) {
      ctx.fillStyle='#e75a3e';
      for (const p of frame.scan) if (point(p)) {ctx.beginPath();ctx.arc(p[0],p[1],1.6*ratio/scale,0,Math.PI*2);ctx.fill();}
    }
    if (frame && layers.pose && point(frame.pose) && finite(frame.pose[2])) {
      const [x,y,a]=frame.pose, size=Math.max(.14,10*ratio/scale);
      ctx.save();ctx.translate(x,y);ctx.rotate(a);ctx.fillStyle='#16836c';ctx.strokeStyle='#fff';ctx.lineWidth=2*ratio/scale;
      ctx.beginPath();ctx.moveTo(size,0);ctx.lineTo(-size*.7,size*.6);ctx.lineTo(-size*.45,0);ctx.lineTo(-size*.7,-size*.6);ctx.closePath();ctx.fill();ctx.stroke();
      ctx.strokeStyle='#16836c';ctx.lineWidth=1.5*ratio/scale;ctx.setLineDash([3*ratio/scale,3*ratio/scale]);
      if (state.reference!==null) {ctx.rotate(state.reference-a);ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(size*2,0);ctx.stroke();}
      ctx.restore();
    }
    ctx.setTransform(1,0,0,1,0,0);
    const bar=Math.max(.5,Math.pow(10,Math.floor(Math.log10((width/scale)*.2))));
    ctx.strokeStyle='#435c70';ctx.lineWidth=2*ratio;ctx.beginPath();ctx.moveTo(22*ratio,height-24*ratio);ctx.lineTo(22*ratio+bar*scale,height-24*ratio);ctx.stroke();
    ctx.fillStyle='#435c70';ctx.font=12*ratio+'px sans-serif';ctx.fillText(bar+' m',22*ratio,height-32*ratio);
    $('empty').hidden=!!(state.map || frame && (point(frame.pose) || frame.scan && frame.scan.length));
    if (!framesReady()) text('empty','等待第一帧 · 地图与位置会在算法就绪后显示');
  }
  function framesReady() {return data.frames.length>0;}
  function render() {
    const state=snapshot(data,index),frame=state.frame,status=state.status;
    text('mode', live ? (follow ? '实时监看' : '回看记录') : '离线回放');
    const scene=data.scenario || {};
    const sceneNames={baseline:'原房间',l_shape:'L 形房间',clutter:'家具房间',bent_passage:'弯通道',recess:'凹角房间'};
    text('scenario',(sceneNames[scene.id] || scene.name || '等待场景信息')+
      (Number.isInteger(scene.spawn_index) ? ' · 起点 '+scene.spawn_index : '')+' · 算法估计 / map 坐标');
    text('mission',states[status.state] || (status.state ? String(status.state) : '等待任务状态'));
    $('mission').className='state '+(['completed','completed_with_residual_frontiers'].includes(status.state) ? 'good' : ['failed','map_unstable','incomplete','interrupted'].includes(status.state) ? 'warning' : '');
    text('reason',reasons[status.reason] || status.reason || '等待探索任务发布状态');
    text('saved',status.map_saved===true ? '已保存' : status.map_saved===false ? '未保存' : '尚无结果');
    text('returned',status.returned===true ? '已返回' : status.returned===false ? '未返回' : '尚无结果');
    text('position',frame && point(frame.pose) ? number(frame.pose[0])+' / '+number(frame.pose[1])+' m' : '暂无有效估计');
    text('heading',state.relativeAngle!==null ? (state.relativeAngle>0 ? '+' : '')+number(state.relativeAngle,1,'°') : '暂无有效估计');
    text('distance',number(state.distance,2,' m'));
    text('map-version',state.map ? '第 '+(frame.map+1)+' 版' : '尚未收到');
    text('scan-age',frame && frame.scan ? number(frame.scan_age_s,2,' s') : '无有效激光');
    text('plan-age',frame && frame.plan && frame.plan.length ? number(frame.plan_age_wall_s,1,' s')+(frame.plan_age_wall_s>5 ? ' · 旧路线' : '') : '尚无路线');
    text('issues',(frame && frame.issues || []).map(issue=>issues[issue] || String(issue)).join('；'));
    text('time',frame ? '模拟 '+number(frame.t,1,' s')+' · '+(index+1)+' / '+data.frames.length+' 帧' : '尚无数据');
    $('timeline').max=Math.max(0,data.frames.length-1);$('timeline').value=index;
    $('play').disabled=!framesReady();$('timeline').disabled=!framesReady();
    $('play').textContent=playing ? '暂停' : '播放';$('follow').hidden=!live;
    sourceStatus();assessment();draw(state);
    root.WheeltecViewerState={index,frameCount:data.frames.length,follow,playing,selectedTime:frame && frame.t,mission:status.state || null,
      mapIndex:frame && frame.map,trajectoryPoints:state.segments.reduce((n,p)=>n+p.length,0),freshness:freshness(performance.now(),lastAdvance,lastFetchError)};
  }
  function setIndex(value) {index=Math.max(0,Math.min(Number(value),data.frames.length-1));follow=false;playing=false;render();}
  $('timeline').addEventListener('input',event=>setIndex(event.target.value));
  $('first').addEventListener('click',()=>setIndex(0));
  $('play').addEventListener('click',()=>{playing=!playing;follow=false;playTime=data.frames[index].t;lastTick=null;render();});
  $('follow').addEventListener('click',()=>{follow=true;playing=false;index=Math.max(0,data.frames.length-1);render();});
  $('fit').addEventListener('click',render);
  document.querySelectorAll('[data-layer]').forEach(input=>input.addEventListener('change',()=>{layers[input.dataset.layer]=input.checked;render();}));
  window.addEventListener('resize',()=>draw(snapshot(data,index)));
  async function refresh() {
    try {
      const response=await fetch('process.json',{cache:'no-store'});
      if (!response.ok) throw new Error('process unavailable');
      const next=await response.json();
      if (next.version!==1 || next.coordinate_frame!=='map' || !Array.isArray(next.frames) || !Array.isArray(next.maps)) throw new Error('schema');
      const last=next.frames[next.frames.length-1];
      const key=next.frames.length+':'+(last && last.t)+':'+(last && last.wall_t);
      if (key!==signature) {signature=key;lastAdvance=performance.now();}
      data=next;lastFetchError=false;
      if (follow) index=Math.max(0,data.frames.length-1);
      else index=Math.min(index,Math.max(0,data.frames.length-1));
      try {
        const assessmentResponse=await fetch('result.json',{cache:'no-store'});
        result=assessmentResponse.ok ? await assessmentResponse.json() : null;
      } catch (_) { /* Keep an already loaded final assessment during disconnection. */ }
      render();
    } catch (_) {
      lastFetchError=true;sourceStatus();
      if (!framesReady()) text('empty','正在等待过程记录 · 首次启动约需数秒');
    }
  }
  function animate(now) {
    if (playing && framesReady()) {
      if (lastTick!==null) playTime+=(now-lastTick)/1000*Number($('speed').value);
      lastTick=now;
      let next=index;
      while (next+1<data.frames.length && data.frames[next+1].t<=playTime) next++;
      if (next!==index) {index=next;render();}
      if (index===data.frames.length-1) {playing=false;lastTick=null;render();}
    } else lastTick=null;
    requestAnimationFrame(animate);
  }
  render();requestAnimationFrame(animate);
  if (live) {refresh();setInterval(refresh,5000);setInterval(sourceStatus,1000);}
})(typeof globalThis!=='undefined' ? globalThis : this);
