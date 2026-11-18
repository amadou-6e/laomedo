import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage({viewport:{width:1206,height:1056},colorScheme:'dark'});
 await page.goto('http://127.0.0.1:55895/flow/261e3372-8b8d-440f-bb3d-73fb785d5c2d');
 await page.getByRole('button',{name:'Agents',exact:true}).click({timeout:90000});
 await page.getByRole('button',{name:'Laomedo Codex Agent · completed',exact:true}).click();
 await page.getByRole('button',{name:'Search conversation',exact:true}).waitFor();
 const dir='C:/CodeWorkspace/laomedo/.tools/activity-295-render';await mkdir(dir,{recursive:true});
 await page.getByRole('heading',{name:'Usage and diagnostics'}).scrollIntoViewIfNeeded();
 await page.screenshot({path:dir+'/closed.png'});
 await page.getByRole('button',{name:'Search conversation',exact:true}).click();
 const input=page.getByRole('textbox',{name:'Search conversation',exact:true});
 if(!await input.evaluate(el=>el===document.activeElement))throw Error('Missing search focus');
 await input.fill('Provider connection works');
 await page.screenshot({path:dir+'/search.png'});
 await input.press('Escape');
 if(await input.count())throw Error('Search remained open');
 await page.getByRole('button',{name:'Search conversation',exact:true}).click();
 if(await input.inputValue()!=='')throw Error('Hidden filter retained');
 await input.press('Escape');
 await page.getByRole('button',{name:'Search OpenTelemetry records',exact:true}).click();
 await page.getByRole('textbox',{name:'Search OpenTelemetry records',exact:true}).press('Escape');
 console.log(JSON.stringify({realRetainedRun:true,collapsedSearch:true,focus:true,escapeClears:true,noInference:true,noMutation:true}));
}finally {await browser.close()}
