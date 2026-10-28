import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root=fileURLToPath(new URL("../../..", import.meta.url));
const out=path.resolve(process.argv[2] || path.join(root,"setup/verification/2026-10-28-night/hz-browser-"+new Date().toISOString().replaceAll(":","-")));
if(fs.existsSync(path.join(out,"results.json")))throw Error("Retain old evidence; choose new run directory");
fs.mkdirSync(out,{recursive:true});
const capture=JSON.parse(fs.readFileSync(path.join(root,"setup/verification/2026-10-28-camera-flicker/timestamps/probe.json"),"utf8"));
const initial=JSON.parse(fs.readFileSync(path.join(root,"setup/verification/2026-10-28-g0/sensors-on-v1/web-state-initial.json"),"utf8"));
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1512,height:1100}});
let index=0, stopped=false, paused=false;
const checks=[],controls=[];
const state={...initial,kind:"robot",connection:{name:"离线回放 · 非实车连接",host:"recorded",username:"",kind:"robot"},maintenance:false,logs:[],pose:null,laser_pose:null,clock:946686540,control:{...initial.control,mine:false,ready:false,enabled:false,limits:[.1,.3],target:[0,0],output:[0,0]}};
await page.route("**/api/v1/**",route=>{
 if(route.request().url().endsWith("/camera"))
  return route.fulfill({status:200,contentType:"image/png",body:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=","base64")});
 return route.fulfill({json:{}});
});
await page.routeWebSocket("**/api/v1/events",ws=>{
 const timer=setInterval(()=>{
  if(paused)return;
  const recorded=capture.states[index++%capture.states.length];
  state.streams.camera={...recorded,receiving:!stopped,receive_age:stopped?2:.05,receive_hz:7.5};
  ws.send(JSON.stringify({type:"state",data:state}));
 },150);
 timer.unref();
 ws.onMessage(raw=>controls.push(JSON.parse(raw.toString())));
 ws.onClose(()=>clearInterval(timer));
});
async function check(name,body){
 try{await body();checks.push({name,passed:true});}
 catch(e){checks.push({name,passed:false,error:String(e)});}
}
await page.goto("http://127.0.0.1:8766");
const metric=page.locator(".metric").filter({hasText:"相机"});
await metric.locator("strong").filter({hasText:"7.5"}).waitFor({timeout:10000});
await check("recorded future-stamp oscillation never hides Hz",async()=>{
 const samples=[];
 for(let i=0;i<60;i++){samples.push(await metric.locator("strong").innerText());await page.waitForTimeout(100);}
 fs.writeFileSync(path.join(out,"samples.json"),JSON.stringify(samples));
 if(samples.some(x=>!x.includes("7.5")))throw Error("Hz disappeared during capture timestamp error");
});
await check("warning remains distinct from receive-rate",async()=>{
 await page.getByText(/已检测到相机采集时间戳异常/).waitFor({timeout:3000});
});
await page.screenshot({path:path.join(out,"offline-replay.png"),fullPage:true});
await check("real video reception stop hides rate",async()=>{
 stopped=true;await page.waitForTimeout(500);
 if(!(await metric.locator("strong").innerText()).includes("—"))throw Error("Stale Hz still displayed");
 stopped=false;
});
await check("offline state channel never shows cached rate",async()=>{
 paused=true;await page.waitForTimeout(1600);
 if(!(await metric.locator("strong").innerText()).includes("—"))throw Error("Offline cached Hz still displayed");
 paused=false;
});
await check("recovery resumes current receive frequency",async()=>{
 await metric.locator("strong").filter({hasText:"7.5"}).waitFor({timeout:4000});
});
await check("no motion requests",async()=>{
 if(controls.some(m=>m.type==="control"&&!["release","stop"].includes(m.data?.action)))throw Error("Unexpected control operation");
});
const result={source:"OFFLINE UI replay: recorded capture-stamp oscillation; synthetic 7.5 Hz reception and 1-pixel video fixture; no live robot connection",checks,passed:checks.filter(x=>x.passed).length,total:checks.length};
fs.writeFileSync(path.join(out,"results.json"),JSON.stringify(result,null,2));
console.log(JSON.stringify(result));await browser.close();
if(result.passed!==result.total)process.exitCode=1;
