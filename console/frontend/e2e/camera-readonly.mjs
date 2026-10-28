import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const out = path.resolve(process.argv[2] || "../../setup/verification/2026-10-28-camera-flicker/browser-" + new Date().toISOString().replaceAll(":", "-"));
if (fs.existsSync(path.join(out, "results.json"))) throw Error("Use a new output directory; retain prior results");
fs.mkdirSync(out, {recursive:true});
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1512,height:1100}});
const checks = [];
let videoStopped = false;
await page.routeWebSocket("**/api/v1/events", ws => {
  const server = ws.connectToServer();
  server.onMessage(raw => {
    const message = JSON.parse(raw.toString());
    if (message.type === "state") {
      if (message.data.control.enabled) throw Error("Read-only robot required");
      if (videoStopped) {
        message.data.streams.camera.receiving = false;
        message.data.streams.camera.fresh = false;
      }
    }
    ws.send(JSON.stringify(message));
  });
  ws.onMessage(raw => {
    const m = JSON.parse(raw.toString());
    if (m.type === "control" && !["release","stop"].includes(m.data.action))
      throw Error("Motion interface must not be used");
    server.send(raw);
  });
});
await page.addInitScript(() => {
  window.probe = {frames:0,blank:0,visible:0,placeholders:0,revokedDisplayed:0,requests:[]};
  const revoke = URL.revokeObjectURL.bind(URL);
  URL.revokeObjectURL = url => {
    if(document.querySelector(".camera img")?.getAttribute("src") === url)
      window.probe.revokedDisplayed++;
    revoke(url);
  };
  const sample = () => {
    const p=window.probe, img=document.querySelector(".camera img");
    p.frames++;
    if(img) {p.visible++; if(!img.complete || !img.naturalWidth) p.blank++;}
    else if(document.querySelector(".camera")) p.placeholders++;
    requestAnimationFrame(sample);
  };
  requestAnimationFrame(sample);
});
page.on("response", r => {
  if(r.url().endsWith("/api/v1/camera"))
    page.evaluate(status => window.probe.requests.push({status}), r.status()).catch(()=>{});
});
async function check(name, run) {
  try {await run(); checks.push({name,passed:true});}
  catch(e) {checks.push({name,passed:false,error:String(e)});}
}
const image = page.locator(".camera img");
await page.goto("http://127.0.0.1:8766");
await image.waitFor({state:"visible",timeout:15000});
await page.waitForTimeout(1000);
await page.evaluate(()=>Object.assign(window.probe,{frames:0,blank:0,visible:0,placeholders:0,revokedDisplayed:0,requests:[]}));
await page.waitForTimeout(16000);
const live = await page.evaluate(()=>window.probe);
await check("live ROS video has no blank/placeholder frames or HTTP failures", async()=>{
 if(live.blank || live.placeholders || live.requests.some(r=>r.status!==200) || live.requests.length<10)
   throw Error(JSON.stringify(live));
});
await check("displayed blob URLs survive until replacement",async()=>{
 if(live.revokedDisplayed) throw Error("Displayed frame revoked");
});
await check("capture timestamp anomaly remains explicitly visible",async()=>{
 if(!await page.getByText(/已检测到相机采集时间戳异常/).isVisible()) throw Error("Missing warning");
});
await page.screenshot({path:path.join(out,"live.png"),fullPage:true});
await check("HTTP video failure hides image; recovery resumes it",async()=>{
 await page.route("**/api/v1/camera",route=>route.fulfill({status:503,body:""}));
 await image.waitFor({state:"hidden",timeout:3000});
 await page.unroute("**/api/v1/camera");
 await image.waitFor({state:"visible",timeout:5000});
});
await check("video reception loss hides cached image",async()=>{
 videoStopped=true;
 await image.waitFor({state:"hidden",timeout:3000});
 videoStopped=false;
 await image.waitFor({state:"visible",timeout:5000});
});
await check("slow requests stay serialized",async()=>{
 let active=0, peak=0;
 await page.route("**/api/v1/camera",async route=>{
   active++;peak=Math.max(peak,active);
   await new Promise(resolve=>setTimeout(resolve,800));
   await route.continue();active--;
 });
 await page.waitForTimeout(3500);
 await page.unroute("**/api/v1/camera",{behavior:"wait"});
 if(peak!==1) throw Error("Concurrent camera requests: "+peak);
});
await check("browser offline hides video; reconnect resumes without control",async()=>{
 await page.context().setOffline(true);
 await image.waitFor({state:"hidden",timeout:4000});
 await page.context().setOffline(false);
 await image.waitFor({state:"visible",timeout:10000});
});
const result={host_utc:new Date().toISOString(),source:"live robot ROS camera; faults injected only in isolated browser",motion_commands:0,live,checks,passed:checks.filter(x=>x.passed).length,total:checks.length};
fs.writeFileSync(path.join(out,"results.json"),JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
await browser.close();
if(result.passed!==result.total)process.exitCode=1;
