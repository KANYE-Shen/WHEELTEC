import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';
const out=path.resolve(process.argv[2]);fs.mkdirSync(out,{recursive:true});
if(fs.existsSync(path.join(out,'results.json')))throw Error('Use a new output directory');
const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1512,height:1100}});
const controls=[],tasks=[],checks=[],errors=[],terminalInput=[];let epoch=0,socket=null,timer=null,claimDelay=0;
let data={kind:'robot',clock:Date.now()/1000,connected:true,maintenance:false,connection:{name:'isolated UI fixture',host:'fixture',username:'fixture',kind:'robot'},task:{mode:'remote',error:''},streams:{scan:{stamp:1,age:0,hz:10,fresh:true},odom:{stamp:1,age:0,hz:20,fresh:true},map:{stamp:1,age:0,hz:1,fresh:true},camera:{stamp:null,age:null,hz:0,fresh:false,receiving:false}},scan:{frame:'laser',angle_min:0,angle_increment:1,range_min:.15,range_max:10,ranges:[1,2,3]},pose:{x:0,y:0,yaw:0,age:0,frame:'map'},laser_pose:null,odom:{linear:0,angular:0,frame:'odom'},logs:[],control:{epoch:0,gear:1,selection_mode:'hold',mine:false,ready:false,reason:'operator_hold',enabled:true,target:[0,0],output:[0,0],command_timeout:.5,heartbeat_timeout:.5,limits:[.1,.3],watchdog:{armed:false},watchdog_fresh:true,watchdog_revision:1}};
function emit(){data.control.epoch=epoch;socket?.send(JSON.stringify({type:'state',data}));}
function remote(){epoch++;data.task.mode='remote';data.control.mine=false;data.control.ready=false;data.control.selection_mode='hold';data.control.watchdog.armed=false;emit();}
page.on('pageerror',e=>errors.push(String(e)));
await page.routeWebSocket('**/api/v1/events',ws=>{
 socket=ws;timer=setInterval(emit,50);
 ws.onMessage(raw=>{const m=JSON.parse(raw.toString());if(m.type!=='control')return;const c=m.data;controls.push(c);
  if(c.action==='stop'||c.action==='release')remote();
  if(c.action==='claim'){
   const ticket=epoch;data.control.mine=true;emit();
   setTimeout(()=>{if(ticket!==epoch)return;data.control.ready=true;data.control.selection_mode='manual';data.control.watchdog.armed=true;emit();},claimDelay);
  }
  if(c.action==='gear'){data.control.gear=Math.max(0,Math.min(2,data.control.gear+c.delta));emit();}
 });ws.onClose(()=>clearInterval(timer));
});
await page.routeWebSocket('**/api/v1/terminal',ws=>{ws.onMessage(raw=>terminalInput.push(JSON.parse(raw.toString())));});
await page.route('**/api/v1/task',async route=>{
 const body=route.request().postDataJSON();tasks.push(body);if(body.action==='explore'){
  const ticket=++epoch;data.task.mode='starting';data.control.gear=1;emit();
  await new Promise(r=>setTimeout(r,350));if(ticket===epoch){data.task.mode='autonomous';emit();}
 }else if(body.action==='reset_map'){remote();data.map_reset={busy:true,error:'',sequence:0};emit();await new Promise(r=>setTimeout(r,700));delete data.map;data.map_reset={busy:false,error:'',sequence:1};emit();}else remote();
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data.task)});
});
async function check(name,fn){try{await fn();checks.push({name,passed:true});}catch(e){checks.push({name,passed:false,error:String(e)});}}
try{
 await page.goto('http://127.0.0.1:8766');await expect(page.getByText('数据通道在线',{exact:true})).toBeVisible();
 const mode=page.getByLabel('当前控制模式'),gear=page.getByLabel('速度挡位',{exact:true});
 await check('view reset centers the robot arrow',async()=>{
  data.pose={x:3,y:-2,yaw:0,age:0,frame:'map'};data.laser_pose={...data.pose};
  data.map={revision:1,frame:'map',width:32,height:32,resolution:.05,origin:[2.2,-2.8,0],data:Array(1024).fill(100)};emit();
  await page.getByRole('button',{name:'重置视图',exact:true}).click();await page.waitForTimeout(100);
  const center=await page.getByLabel('占据栅格地图与雷达').evaluate(canvas=>{
   const d=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;let xs=[],ys=[];
   for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){let i=(y*canvas.width+x)*4;if(d[i]===255&&d[i+1]===204&&d[i+2]===118){xs.push(x);ys.push(y);}}
   return {count:xs.length,x:((Math.min(...xs)+Math.max(...xs))/2-canvas.width/2),y:((Math.min(...ys)+Math.max(...ys))/2-canvas.height/2)};
  });expect(center.count).toBeGreaterThan(20);expect(Math.abs(center.x)).toBeLessThan(5);expect(Math.abs(center.y)).toBeLessThan(3);
 });
 await check('Reset requests stopped map reset and hides the old grid',async()=>{
  await page.getByRole('button',{name:'Reset',exact:true}).click();await expect(page.getByRole('button',{name:'重置地图中…'})).toBeDisabled();
  const oldPixels=await page.getByLabel('占据栅格地图与雷达').evaluate(canvas=>{
   const d=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;let count=0;
   for(let i=0;i<d.length;i+=4)if(d[i]===221&&d[i+1]===232&&d[i+2]===233)count++;return count;
  });expect(oldPixels).toBe(0);expect(tasks.at(-1).action).toBe('reset_map');
  await expect(page.getByRole('button',{name:'Reset',exact:true})).toBeEnabled();await expect(mode).toContainText('远程接管');
 });
 await check('two buttons and three speed gears',async()=>{
  await expect(page.getByRole('button',{name:'自主探索',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'远程接管',exact:true})).toBeVisible();
  await expect(gear).toContainText('中挡');await page.getByRole('button',{name:'降低速度挡位'}).click();
  await expect(gear).toContainText('低挡');await expect(gear).toContainText('0.03 m/s');
  await page.getByRole('button',{name:'提高速度挡位'}).click();await page.getByRole('button',{name:'提高速度挡位'}).click();
  await expect(gear).toContainText('高挡');await expect(gear).toContainText('0.10 m/s');
 });
 await check('autonomous button defaults to middle gear and ignores WASD',async()=>{
  await page.getByRole('button',{name:'自主探索',exact:true}).click();await expect(mode).toContainText('自主探索');
  await expect(gear).toContainText('中挡');const before=controls.filter(x=>x.action==='command').length;
  await page.keyboard.down('w');await page.waitForTimeout(150);await page.keyboard.up('w');
  expect(controls.filter(x=>x.action==='command').length).toBe(before);expect(tasks.at(-1).action).toBe('explore');
 });
 await check('Space works inside a text input and returns remote',async()=>{
  await page.getByLabel('筛选日志').focus();const before=controls.filter(x=>x.action==='stop').length;
  await page.keyboard.press('Space');await expect(mode).toContainText('远程接管');
  expect(controls.filter(x=>x.action==='stop').length).toBeGreaterThan(before);
 });
 await check('Space preempts pending start without automatic resume',async()=>{
  await page.getByRole('button',{name:'自主探索',exact:true}).click();await expect(mode).toContainText('正在启动');
  await page.keyboard.press('Space');await page.waitForTimeout(500);await expect(mode).toContainText('远程接管');
 });
 await check('remote button and WASD need no extra claim button',async()=>{
  await page.getByRole('button',{name:'远程接管',exact:true}).click();await expect(mode).toContainText('远程接管');
  await page.keyboard.down('w');await expect.poll(()=>controls.some(x=>x.action==='command'&&x.linear===.06)).toBe(true);
  await page.keyboard.up('w');await expect.poll(()=>controls.filter(x=>x.action==='command').at(-1)?.linear).toBe(0);
  await page.keyboard.press('Space');
 });
 await check('delayed acknowledgment renews only zero before allowing held W',async()=>{
  claimDelay=1500;remote();await page.waitForTimeout(100);const before=controls.length;
  await page.keyboard.down('w');await page.waitForTimeout(1100);
  const waiting=controls.slice(before).filter(x=>x.action==='command');
  expect(waiting.length).toBeGreaterThan(2);expect(waiting.every(x=>x.linear===0&&x.angular===0)).toBe(true);
  await expect.poll(()=>controls.slice(before).some(x=>x.action==='command'&&x.linear===.06),{timeout:3000}).toBe(true);
  await page.keyboard.up('w');await page.keyboard.press('Space');
 });
 await check('Space cancels held W during delayed arm without later movement',async()=>{
  remote();await page.waitForTimeout(100);await page.keyboard.down('w');await page.waitForTimeout(250);
  await page.keyboard.press('Space');await page.keyboard.up('w');const before=controls.length;
  await page.waitForTimeout(1700);expect(data.control.watchdog.armed).toBe(false);
  expect(controls.slice(before).some(x=>x.action==='command'&&(x.linear||x.angular))).toBe(false);
  expect(tasks.at(-1).action).toBe('stop');claimDelay=0;
 });
 await check('Space remains active in the SSH terminal',async()=>{
  await page.getByRole('button',{name:'⌘　SSH 终端',exact:true}).click();
  await expect(page.getByRole('heading',{name:'SSH 维护终端'})).toBeVisible();
  const before=controls.filter(x=>x.action==='stop').length;await page.keyboard.press('Space');
  await expect.poll(()=>controls.filter(x=>x.action==='stop').length).toBeGreaterThan(before);
  expect(terminalInput.filter(x=>x.type==='input'&&x.data.includes(' '))).toHaveLength(0);
 });
 await check('no browser runtime error',async()=>expect(errors).toEqual([]));
 await page.screenshot({path:path.join(out,'fixture.png'),fullPage:true});
}finally{clearInterval(timer);await browser.close();}
const result={source:'isolated browser fixture; all task/control/terminal writes intercepted; no real robot commands',checks,passed:checks.filter(x=>x.passed).length,total:checks.length,errors,tasks,controls};
fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({passed:result.passed,total:result.total,checks}));process.exitCode=result.passed===result.total?0:1;
