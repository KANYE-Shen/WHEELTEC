import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const out=path.resolve(process.argv[2]);fs.mkdirSync(out,{recursive:true});
if(fs.existsSync(path.join(out,'result.json')))throw Error('Use a new output directory');
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1512,height:1100}});
const errors=[],checks=[],writes=[];let timer;
const data={kind:'robot',clock:Date.now()/1000,connected:true,maintenance:false,
 task:{mode:'remote',error:''},map_reset:{busy:false,error:'',sequence:0},
 streams:Object.fromEntries(['scan','odom','map','camera'].map(k=>[k,{fresh:k!=='camera',receiving:false,age:0,hz:10,stamp:1}])),
 scan:{frame:'laser',angle_min:0,angle_increment:1,range_min:.2,range_max:10,ranges:[1,2,3]},
 map:{revision:1,frame:'map',width:32,height:32,resolution:.05,origin:[-.8,-.8,0],data:Array(1024).fill(0)},
 pose:{x:0,y:0,yaw:0,age:0,frame:'map'},laser_pose:{x:0,y:0,yaw:0,age:0,frame:'map'},
 odom:{linear:0,angular:0,frame:'odom'},logs:[],
 control:{epoch:0,gear:1,selection_mode:'hold',mine:false,ready:false,reason:'operator_hold',
 enabled:true,target:[0,0],output:[0,0],command_timeout:.5,heartbeat_timeout:.5,limits:[.1,.3],
 watchdog:{armed:false},watchdog_fresh:true,watchdog_revision:1}};
page.on('pageerror',e=>errors.push({message:e.message,stack:e.stack}));
await page.routeWebSocket('**/api/v1/events',ws=>{
 timer=setInterval(()=>ws.send(JSON.stringify({type:'state',data})),50);
 ws.onMessage(raw=>writes.push(JSON.parse(raw.toString())));ws.onClose(()=>clearInterval(timer));
});
await page.route('**/api/v1/**',route=>{
 if(route.request().method()!=='GET')writes.push({url:route.request().url(),body:route.request().postData()});
 return route.fulfill({status:200,contentType:'application/json',body:'{}'});
});
async function check(name,fn){try{await fn();checks.push({name,passed:true});}catch(e){checks.push({name,passed:false,error:String(e)});}}
async function arrowCenter(){
 return page.getByLabel('占据栅格地图与雷达').evaluate(canvas=>{
  const d=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
  let x0=canvas.width,y0=canvas.height,x1=-1,y1=-1;
  for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){
   const i=(y*canvas.width+x)*4;if(d[i]===255&&d[i+1]===204&&d[i+2]===118){x0=Math.min(x,x0);x1=Math.max(x,x1);y0=Math.min(y,y0);y1=Math.max(y,y1);}
  }
  return {x:(x0+x1)/2,y:(y0+y1)/2};
 });
}
async function burst(endType='pointerup'){
 const canvas=page.getByLabel('占据栅格地图与雷达'),box=await canvas.boundingBox();
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
 await canvas.evaluate((el,kind)=>{
  const r=el.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;
  for(let i=1;i<=25;i++)el.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerId:1,buttons:1,clientX:x+i*4,clientY:y-i*2}));
  el.dispatchEvent(new PointerEvent(kind,{bubbles:true,pointerId:1,buttons:0,clientX:x+100,clientY:y-50}));
 },endType);
 if(endType==='pointerup')await page.mouse.up();await page.waitForTimeout(100);
}
try{
 await page.goto('http://127.0.0.1:8766');await expect(page.getByText('数据通道在线',{exact:true})).toBeVisible();
 await check('simple canvas click keeps the application mounted',async()=>{
  await page.getByLabel('占据栅格地图与雷达').click();await expect(page.getByRole('heading',{name:'空间视图',exact:true})).toBeVisible();
 });
 const before=await arrowCenter();
 await check('batched pointer moves followed by release do not black out the page',async()=>{
  await burst();await expect(page.getByRole('heading',{name:'空间视图',exact:true})).toBeVisible({timeout:1500});expect(errors).toEqual([]);
 });
 if(checks.at(-1).passed){
  await check('batched drag preserves its complete displacement',async()=>{
   const after=await arrowCenter();expect(after.x-before.x).toBeCloseTo(100,0);expect(after.y-before.y).toBeCloseTo(-50,0);
  });
  for(const endType of ['pointercancel','lostpointercapture'])await check(endType+' stops dragging before physical release',async()=>{
   await burst(endType);const before=await arrowCenter();
   await page.getByLabel('占据栅格地图与雷达').evaluate(el=>el.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerId:1,buttons:1,clientX:15,clientY:15})));
   await page.waitForTimeout(100);expect(await arrowCenter()).toEqual(before);expect(errors).toEqual([]);await page.mouse.up();
  });
  await check('repeated drag, zoom, centering and layer switches keep controls visible',async()=>{
   for(let i=0;i<4;i++){
    await page.getByRole('button',{name:'重置视图',exact:true}).click();await burst();
    await page.getByRole('button',{name:'放大视图',exact:true}).click();await page.getByRole('button',{name:'缩小视图',exact:true}).click();
    await page.getByRole('checkbox',{name:'占据栅格',exact:true}).uncheck();await page.getByRole('checkbox',{name:'占据栅格',exact:true}).check();
    await page.getByRole('button',{name:'局部雷达',exact:true}).click();await page.getByRole('button',{name:'地图叠加',exact:true}).click();
   }
   await expect(page.getByRole('button',{name:'软件停车',exact:true})).toBeVisible();expect(errors).toEqual([]);
  });
 }
 await page.screenshot({path:path.join(out,'page.png'),fullPage:true});
}finally{clearInterval(timer);await browser.close();}
const result={source:'local fixture; every API and websocket write intercepted; no SSH or robot access',checks,errors,writes,passed:checks.filter(x=>x.passed).length,total:checks.length};
fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));process.exitCode=result.passed===result.total?0:1;
