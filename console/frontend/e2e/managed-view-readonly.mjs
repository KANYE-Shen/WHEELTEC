import { chromium, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const out = path.resolve(process.argv[2]);
if (fs.existsSync(path.join(out, "results.json"))) throw Error("Retain previous results; use a new directory");
fs.mkdirSync(out, {recursive:true});
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1512,height:1100}});
const checks=[], errors=[], forbidden=[]; let latest=null;
page.on("pageerror", e=>errors.push(String(e)));
await page.routeWebSocket("**/api/v1/events", ws=>{
 const server=ws.connectToServer();
 server.onMessage(raw=>{const m=JSON.parse(raw.toString());if(m.type==="state") latest=m.data;ws.send(raw);});
 ws.onMessage(raw=>{const m=JSON.parse(raw.toString());if(m.type==="control"){forbidden.push(m);throw Error("Read-only test must not issue controls");}server.send(raw);});
});
async function check(name, fn){try{await fn();checks.push({name,passed:true});}catch(e){checks.push({name,passed:false,error:String(e)});}}
try {
 await page.goto("http://127.0.0.1:8766");
 await expect(page.getByText("数据通道在线",{exact:true})).toBeVisible({timeout:15000});
 await check("SSH connection form and credential fields removed",async()=>{
  await expect(page.getByRole("button",{name:"连接设置",exact:true})).toHaveCount(0);
  await expect(page.locator('input[type="password"], input[aria-label="fingerprint"]')).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"SSH 连接",exact:true})).toHaveCount(0);
 });
 await check("real robot connection and live scan remain read-only",async()=>{
  expect(latest.kind).toBe("robot");expect(latest.control.enabled).toBe(false);
  expect(latest.streams.scan.fresh).toBe(true);expect(latest.scan.ranges.length).toBeGreaterThan(0);
  expect(latest.connection.host).toBe("192.168.0.100");
 });
 const plus=page.getByRole("button",{name:"放大视图",exact:true});
 const minus=page.getByRole("button",{name:"缩小视图",exact:true});
 const zoom=page.getByLabel("视图缩放比例");
 const reset=page.getByRole("button",{name:"重置视图",exact:true});
 const canvas=page.getByLabel("占据栅格地图与雷达");
 await check("plus and minus control zoom",async()=>{
  await expect(zoom).toHaveText("100%");await plus.click({timeout:1500});await expect(zoom).toHaveText("120%");
  await minus.click({timeout:1500});await expect(zoom).toHaveText("100%");
 });
 await check("wheel scroll does not zoom radar",async()=>{
  await canvas.hover();await page.mouse.wheel(0,-400);await page.waitForTimeout(300);await expect(zoom).toHaveText("100%",{timeout:1000});
 });
 await check("drag and reset remain available",async()=>{
  const b=await canvas.boundingBox();expect(b).toBeTruthy();await page.mouse.move(b.x+100,b.y+100);await page.mouse.down();await page.mouse.move(b.x+140,b.y+125);await page.mouse.up();
  await plus.click({timeout:1500});await reset.click();await expect(zoom).toHaveText("100%");
 });
 await check("zoom stays bounded and limits disable controls",async()=>{
  for(let i=0;i<30;i++){if(await plus.isDisabled())break;await plus.click({timeout:1500});}
  await expect(plus).toBeDisabled({timeout:1000});await expect(zoom).toHaveText("603%");
  for(let i=0;i<40;i++){if(await minus.isDisabled())break;await minus.click({timeout:1500});}
  await expect(minus).toBeDisabled({timeout:1000});await expect(zoom).toHaveText("21%");await reset.click();await expect(zoom).toHaveText("100%");
 });
 await check("browser has no runtime errors or control requests",async()=>{expect(errors).toEqual([]);expect(forbidden).toEqual([]);});
 await page.screenshot({path:path.join(out,"live.png"),fullPage:true});
} finally {await browser.close();}
const result={source:"live robot ROS through existing authenticated gateway; no mock data",checks,passed:checks.filter(x=>x.passed).length,total:checks.length,errors,forbidden_control_requests:forbidden.length};
fs.writeFileSync(path.join(out,"results.json"),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
process.exitCode=result.passed===result.total?0:1;
