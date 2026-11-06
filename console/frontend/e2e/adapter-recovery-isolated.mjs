import {chromium} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
let ws, posted, submitted, finishConnect, unwanted=[];const errors=[];
page.on('pageerror',e=>errors.push(String(e)));
await page.route('**/*',r=>{
 const pathname=new URL(r.request().url()).pathname;
 const file=pathname==='/'?'index.html':pathname.slice(1);
 return r.fulfill({body:fs.readFileSync(path.join('console/frontend/dist',file)),contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html'});
});
await page.route('**/bootstrap',r=>r.fulfill({json:{version:1}}));
await page.route('**/api/v1/task',r=>{unwanted.push(r.request().postDataJSON());return r.fulfill({json:{}})});
await page.route('**/api/v1/connect-robot',async r=>{
 submitted=r.request().postDataJSON();
 ws.send(JSON.stringify({type:'offline',data:{logs:[],adapter_recovery:true,preparation:'services'}}));
 await new Promise(resolve=>finishConnect=resolve);
 await r.fulfill({status:503,json:{detail:'自动停车准备未完成：sample diagnostic'}});
 ws.send(JSON.stringify({type:'offline',data:{logs:[],adapter_recovery:true,preparation:null}}));
});
await page.route('**/api/v1/adapter/diagnostics',r=>r.fulfill({json:{status:'inspected',missing_services:[],log_tail:'Adapter exited: sample diagnostic'}}));
await page.route('**/api/v1/robot/prepare',async r=>{posted=r.request().postDataJSON();await r.fulfill({json:{connected:true,kind:'robot'}})});
await page.routeWebSocket('**/api/v1/events',s=>{ws=s;s.send(JSON.stringify({type:'offline',data:{logs:[],adapter_recovery:false}}));s.onMessage(m=>unwanted.push(String(m)))});
try{
 await page.goto('http://wheeltec-offline.test/',{waitUntil:'domcontentloaded'});
 await page.getByLabel('小车 SSH 密码').fill('sample');
 await page.getByRole('button',{name:'连接小车',exact:true}).click();
 await page.getByRole('status').filter({hasText:'正在按停车顺序准备原有服务'}).waitFor();
 assert.deepEqual(submitted,{password:'sample'});
 assert.equal(await page.getByRole('button',{name:'正在准备…',exact:true}).isDisabled(),true);
 assert.equal(await page.getByLabel('小车 SSH 密码').count(),0);
 assert.equal(await page.getByRole('checkbox',{name:'小车已停车，允许仅恢复缺失的适配器'}).count(),0);
 finishConnect();
 const restore=page.getByRole('button',{name:'重试停车准备',exact:true});await restore.waitFor();
 await page.getByRole('button',{name:'读取适配器日志',exact:true}).click();
 await page.getByText('Adapter exited: sample diagnostic',{exact:true}).waitFor();
 assert.equal(await restore.isEnabled(),true);
 await page.screenshot({path:'adapter-recovery-preview.png',fullPage:true});
 await restore.click();await page.waitForTimeout(200);
 assert.deepEqual(posted,{confirm_parked:true});
 assert.deepEqual(unwanted,[]);assert.deepEqual(errors,[]);
 console.log('Isolated automatic preparation UI: one password submit, progress, failure logs, fixed retry and no control calls passed');
}finally{await browser.close()}
