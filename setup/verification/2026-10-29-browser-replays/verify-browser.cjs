const fs=require('fs');
const {chromium}=require('D:/虚拟c盘/WHEELTEC/console/frontend/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});const results=[];
 try {
  for(const [name,port,assessment] of [['latest-failure',8778,'未通过'],['historical-reference',8779,'通过']]){
   const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(`http://127.0.0.1:${port}/replay.html`,{waitUntil:'load',timeout:30000});
   await page.waitForFunction(()=>document.querySelector('#timeline').max>0 && document.querySelector('#empty').hidden);
   const check=(label,passed,detail)=>{results.push({name,check:label,passed,detail});if(!passed)throw Error(label)};
   check('real recorded frames render',true,{frames:1+Number(await page.locator('#timeline').getAttribute('max'))});
   check('recorded assessment preserved',(await page.locator('#assessment').innerText())===assessment);
   const first=await page.locator('#time').innerText();
   await page.locator('#timeline').evaluate(el=>{el.value=el.max;el.dispatchEvent(new Event('input',{bubbles:true}))});
   await page.waitForTimeout(100);
   check('timeline changes displayed time',(await page.locator('#time').innerText())!==first);
   await page.locator('[data-layer="scan"]').uncheck();check('laser layer toggles',!(await page.locator('[data-layer="scan"]').isChecked()));
   await page.locator('[data-layer="scan"]').check();await page.locator('#first').click();await page.locator('#speed').selectOption('8');
   await page.locator('#play').click();await page.waitForTimeout(900);
   check('play advances timeline',Number(await page.locator('#timeline').inputValue())>0);
   check('no browser runtime errors',errors.length===0,errors);
   await page.close();
  }
 } finally { await browser.close();fs.writeFileSync('D:/虚拟c盘/WHEELTEC/setup/verification/2026-10-29-browser-replays/browser-checks.json',JSON.stringify({passed:results.filter(x=>x.passed).length,total:results.length,results},null,2)); }
 console.log(JSON.stringify({passed:results.filter(x=>x.passed).length,total:results.length}));
})().catch(e=>{console.error(e);process.exitCode=1});
