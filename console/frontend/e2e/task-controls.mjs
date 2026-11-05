import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';
import { fileURLToPath } from 'node:url';
const dist=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../dist');
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
// Every HTTP request is fulfilled locally. No gateway, SSH or robot is contacted.
await page.route('**/*', async route=>{
 const url=new URL(route.request().url());
 if(url.hostname!=='wheeltec-offline.test')throw Error('Unexpected network request: '+url.origin);
 if(url.pathname==='/bootstrap')return route.fulfill({json:{}});
 if(url.pathname.startsWith('/api/'))return route.fulfill({status:404,body:'offline fixture'});
 const file=path.resolve(dist,'.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));
 if(!file.startsWith(dist+path.sep))throw Error('Static path outside fixture');
 const type=file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html';
 await route.fulfill({body:fs.readFileSync(file),contentType:type});
});
await page.route('**/api/v1/task',async route=>{
 const body=route.request().postDataJSON();tasks.push(body);if(body.action==='explore'){
  const ticket=++epoch;data.task.mode='starting';data.control.gear=1;emit();
  await new Promise(r=>setTimeout(r,350));if(ticket===epoch){data.task.mode='autonomous';data.control.selection_mode='nav';data.control.watchdog.armed=true;data.control.reason='';emit();}
 }else remote();
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data.task)});
});
async function check(name,fn){try{await fn();checks.push({name,passed:true});}catch(e){checks.push({name,passed:false,error:String(e)});}}
try{
 await page.goto('http://wheeltec-offline.test');await expect(page.getByText('数据通道在线',{exact:true})).toBeVisible();
 const mode=page.getByLabel('当前控制模式'),gear=page.getByLabel('速度挡位',{exact:true});
 await check('two buttons and three speed gears',async()=>{
  await expect(page.getByRole('button',{name:'自主探索',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'远程接管',exact:true})).toBeVisible();
  await expect(gear).toContainText('中挡');await page.getByRole('button',{name:'降低速度挡位'}).click();
  await expect(gear).toContainText('低挡');await expect(gear).toContainText('0.03 m/s');
  await page.getByRole('button',{name:'提高速度挡位'}).click();await page.getByRole('button',{name:'提高速度挡位'}).click();
  await expect(gear).toContainText('高挡');await expect(gear).toContainText('0.10 m/s');
 });
 await check('autonomy survives ordinary keys, editable focus and visible blur',async()=>{
  await page.getByRole('button',{name:'自主探索',exact:true}).click();await expect(mode).toContainText('自主探索');
  await expect(gear).toContainText('中挡');const before=tasks.length;
  await page.keyboard.press('x');await page.getByLabel('筛选日志').focus();await page.keyboard.type('warning');
  await page.evaluate(()=>window.dispatchEvent(new Event('blur')));await page.waitForTimeout(300);
  await expect(mode).toContainText('自主探索');expect(tasks.length).toBe(before);
  const heartbeats=controls.filter(x=>x.action==='heartbeat').length;
  await page.evaluate(()=>Object.defineProperty(document,'hasFocus',{configurable:true,value:()=>false}));
  await page.waitForTimeout(450);
  expect(controls.filter(x=>x.action==='heartbeat').length).toBeGreaterThan(heartbeats);
  await expect(mode).toContainText('自主探索');
  await page.evaluate(()=>delete document.hasFocus);
  await page.getByLabel('筛选日志').blur();
 });
 await check('WASD preempts autonomy then waits for confirmed manual readiness',async()=>{
  claimDelay=600;const before=controls.length;
  await page.keyboard.down('w');await expect(mode).toContainText('远程接管');
  await page.waitForTimeout(200);
  expect(controls.slice(before).some(x=>x.action==='command'&&(x.linear||x.angular))).toBe(false);
  await expect.poll(()=>controls.slice(before).some(x=>x.action==='command'&&x.linear===.06)).toBe(true);
  expect(tasks.at(-1).action).toBe('remote');await page.keyboard.up('w');await page.keyboard.press('Space');claimDelay=0;
  await page.getByRole('button',{name:'自主探索',exact:true}).click();await expect(mode).toContainText('自主探索');
  await page.screenshot({path:path.join(out,'autonomous-fixture.png'),fullPage:true});
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
 await check('manual blur still stops and released takeover keys cannot drive later',async()=>{
  remote();await page.waitForTimeout(100);await page.keyboard.down('w');
  await expect.poll(()=>data.control.ready).toBe(true);
  await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
  await expect.poll(()=>data.control.watchdog.armed).toBe(false);await page.keyboard.up('w');
  claimDelay=600;await page.getByRole('button',{name:'自主探索',exact:true}).click();
  await expect(mode).toContainText('自主探索');await page.keyboard.down('w');await page.keyboard.up('w');
  const before=controls.length;await page.waitForTimeout(900);
  expect(controls.slice(before).some(x=>x.action==='command'&&(x.linear||x.angular))).toBe(false);
  await page.keyboard.press('Space');claimDelay=0;
 });
 await check('hidden operator page still stops rather than bypassing heartbeat safety',async()=>{
  await page.getByRole('button',{name:'自主探索',exact:true}).click();await expect(mode).toContainText('自主探索');
  await page.evaluate(()=>{
   Object.defineProperty(document,'hidden',{configurable:true,value:true});
   document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(mode).toContainText('远程接管');
  await page.evaluate(()=>delete document.hidden);
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
const result={source:'isolated browser fixture; ALL HTTP and WebSocket requests fulfilled locally; no gateway or robot contacted',checks,passed:checks.filter(x=>x.passed).length,total:checks.length,errors,tasks,controls};
fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({passed:result.passed,total:result.total,checks}));process.exitCode=result.passed===result.total?0:1;
