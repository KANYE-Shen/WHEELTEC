const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const target = path.join(__dirname, 'process_viewer.js');
assert.ok(fs.existsSync(target), 'Replay selection module must exist');
const replay = require(target);
const document = {version:1, coordinate_frame:'map', maps:[{id:'early'},{id:'future'}], path:[[900,900]],
  terminal:{state:'completed'}, capture:{initial_pose:[0,0,Math.PI/2],initial_pose_t:1},
  frames:[
    {t:0,wall_t:0,pose:null,map:null,status:{}},
    {t:1,wall_t:1,pose:[0,0,Math.PI/2],map:0,status:{state:'starting'}},
    {t:2,wall_t:2,pose:[1,1,-Math.PI*3/4],map:1,status:{state:'exploring'}},
    {t:3,wall_t:3,pose:null,map:1,status:{state:'returning'}},
    {t:4,wall_t:4,pose:[2,2,0],map:1,status:{state:'completed'}}
  ]};
let state = replay.snapshot(document, 0);
assert.equal(state.map, null, 'No fallback to a future first map');
assert.equal(state.reference, null, 'Do not reveal future initial pose');
assert.equal(state.status.state, undefined, 'No future terminal status');
state = replay.snapshot(document, 1);
assert.equal(state.map.id, 'early');
assert.deepEqual(state.segments, [[[0,0]]], 'Ignore document.path containing all future poses');
assert.equal(state.status.state, 'starting');
state = replay.snapshot(document, 2);
assert.deepEqual(state.segments, [[[0,0],[1,1]]]);
assert.ok(Math.abs(state.relativeAngle-135)<1e-9, 'Yaw must wrap across -180/+180');
state = replay.snapshot(document, 4);
assert.deepEqual(state.segments, [[[0,0],[1,1]], [[2,2]]], 'Missing estimate breaks the history line');
assert.equal(replay.snapshot({frames:[],maps:[]}, 0).frame, null);
assert.equal(replay.freshness(20000,0,false), 'stalled', 'Saving an unchanged process does not make sensor data current');
assert.equal(replay.freshness(20000,19999,true), 'disconnected');
console.log('Replay time-boundary, missing-data, heading and staleness checks passed');
