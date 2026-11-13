// Local-only multi-frame audit against the same player used by the studio.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {createRequire} from 'node:module';
import {motionMetrics} from './offline_motion.mjs';
import {installCanvasAudit, instrumentModule} from './offline_geometry.mjs';
const [studioArg, projectArg] = process.argv.slice(2);
const studio=path.resolve(studioArg), project=path.resolve(projectArg);
const {chromium}=createRequire(path.join(studio,'package.json'))('playwright');
const within=(root,p)=>{const rel=path.relative(root,p);return !rel.startsWith('..')&&!path.isAbsolute(rel)};
const manifest=(dir,base)=>fs.existsSync(dir)?fs.readdirSync(dir).sort().flatMap(f=>{
 const p=path.join(dir,f);return fs.statSync(p).isDirectory()?manifest(p,base+'/'+f):f.endsWith('.js')&&!f.startsWith('_')?[base+'/'+f]:[];
}):[];
const types={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.woff2':'font/woff2'};
const server=http.createServer((req,res)=>{
 try{
  const url=decodeURIComponent(req.url.split('?')[0]);
  if(url==='/__audit_geometry.mjs'){res.setHeader('Content-Type','text/javascript');return res.end(fs.readFileSync(new URL('./offline_geometry.mjs',import.meta.url)))}
  if(url==='/__manifest'){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify(manifest(path.join(project,'scenes'),'/project/scenes')))}
  const root=url.startsWith('/project/')?project:studio;
  const p=path.resolve(root,url.startsWith('/project/')?url.slice(9):'.'+url);
  if(!within(root,p)||!fs.existsSync(p)||!fs.statSync(p).isFile()){res.writeHead(404);return res.end()}
  if(url==='/engine/rig2d.js'||url==='/engine/core.js'){
   res.setHeader('Content-Type','text/javascript');
   return res.end(instrumentModule(fs.readFileSync(p,'utf8'),url.endsWith('rig2d.js')?'rig':'core'));
  }
  res.setHeader('Content-Type',types[path.extname(p)]||'application/octet-stream');fs.createReadStream(p).pipe(res);
 }catch{res.writeHead(400);res.end()}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
let browser;
try{
 const bundled=fs.existsSync(chromium.executablePath());
 const chrome=['C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'].some(p=>fs.existsSync(p));
 browser=await chromium.launch({...(process.env.PW_CHANNEL?{channel:process.env.PW_CHANNEL}:bundled?{executablePath:chromium.executablePath()}:{channel:chrome?'chrome':'msedge'}),args:['--enable-unsafe-swiftshader']});
 const page=await browser.newPage();const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
 await page.addInitScript(() => {
  window.__auditGeometry = {};
  window.__auditFigureCounts = {};
  window.__auditFigureSeen = () => {
   const id=window.__auditShot;
   if(id)window.__auditFigureCounts[id]=(window.__auditFigureCounts[id]||0)+1;
  };
  window.__auditFinding = message => {
   const id=window.__auditShot;if(!id)return;
   const findings=window.__auditGeometry[id]??={};
   // One bounded record per distinct defect, with its first actual output frame.
   const key=message.split(': length ')[0];
   if(!findings[key])findings[key]={message,frame:window.__auditFrame??0};
  };
 });
 await page.addInitScript('('+installCanvasAudit.toString()+')(window)');
 // Scene code is local; audit must not contact remote assets/services.
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await page.goto(`http://127.0.0.1:${server.address().port}/player.html?scale=0.35`);
 await page.waitForFunction('window.READY || window.BOOT_ERROR',null,{timeout:60000});
 const boot=await page.evaluate(()=>window.BOOT_ERROR);if(boot)throw new Error(boot);
 const dims=await page.evaluate(()=>window.OUT);await page.setViewportSize({width:dims[0],height:dims[1]});
 const shots=await page.evaluate(()=>window.SHOT_LIST);
 const fps=JSON.parse(fs.readFileSync(path.join(project,'config.json'),'utf8')).fps||24;
 const folder=path.join(project,'build','scene_audit');fs.mkdirSync(folder,{recursive:true});
 const results=[];
 for(const shot of shots){
  const samples=[];
  const first=Math.max(0,Math.ceil(shot.start*fps)),last=Math.max(first,Math.ceil(shot.end*fps)-1);
  const sampleFrames=[...new Set([.05,.18,.31,.44,.57,.70,.83,.95].map(f=>Math.round(first+(last-first)*f)))];
  // Every output frame is drawn, not only the snapshots used for motion metrics.
  // Small chunks keep each browser evaluation bounded and process cancellation responsive.
  let next=first;
  for(const frame of sampleFrames){
   while(next<=frame){
    const end=Math.min(frame,next+23);
    await page.evaluate(({from,to})=>{for(let f=from;f<=to;f++){window.__auditFrame=f;window.renderFrame(f)}},{from:next,to:end});
    next=end+1;
   }
   const time=frame/fps;
   const sample=await page.evaluate(({frame})=>{
    window.__auditFrame=frame;window.renderFrame(frame);
    const c=document.querySelector('#main'),ctx=c.getContext('2d');
    const data=ctx.getImageData(0,0,c.width,c.height).data;
    const pixels=[];for(let y=0;y<32;y++)for(let x=0;x<32;x++){
     const px=Math.floor((.08+.84*x/31)*(c.width-1));
     const py=Math.floor((.24+.49*y/31)*(c.height-1));
     const i=(py*c.width+px)*4;pixels.push(data[i],data[i+1],data[i+2]);
    }
    return {pixels,errors:[...window.ERRORS]};
   },{frame});
   const image=path.join(folder,`${shot.id}_${frame}.png`);await page.screenshot({path:image});
   samples.push({...sample,time,image});
  }
  while(next<=last){
   const end=Math.min(last,next+23);
   await page.evaluate(({from,to})=>{for(let f=from;f<=to;f++){window.__auditFrame=f;window.renderFrame(f)}},{from:next,to:end});
   next=end+1;
  }
  const changes=samples.slice(1).map((s,i)=>motionMetrics(samples[i].pixels,s.pixels));
  const motion=Math.max(0,...changes.map(x=>x.residual)),rawMotion=Math.max(0,...changes.map(x=>x.raw));
  const pixels=samples[Math.floor(samples.length/2)].pixels;let mean=pixels.reduce((a,b)=>a+b,0)/pixels.length;
  const spread=Math.sqrt(pixels.reduce((a,b)=>a+(b-mean)**2,0)/pixels.length);
  const errors=[...new Set(samples.flatMap(s=>s.errors).filter(e=>e.includes(shot.id)))];
  const issues=[];if(!shot.ok)issues.push('Missing scene module');if(errors.length)issues.push(...errors);
  if(motion<.008)issues.push('Very little residual motion in action area after compensating for camera movement');
  if(spread<9)issues.push('Action area is nearly uniform; subject or scene detail may be absent');
  results.push({id:shot.id,motion_ratio:+motion.toFixed(4),raw_motion_ratio:+rawMotion.toFixed(4),color_spread:+spread.toFixed(2),issues,
   frames_checked:last-first+1,sample_times:samples.map(s=>s.time),
   runtime_errors:errors,missing:!shot.ok,images:samples.map(s=>s.image)});
 }
 const allErrors=await page.evaluate(()=>[...window.ERRORS]);
 const geometry=await page.evaluate(()=>window.__auditGeometry);
 const figures=await page.evaluate(()=>window.__auditFigureCounts);
 for(const result of results){
  result.figure_draws=figures[result.id]||0;
  result.geometry_findings=Object.values(geometry[result.id]||{});
  for(const finding of result.geometry_findings)
   result.issues.push(`Frame ${finding.frame} (${(finding.frame/fps).toFixed(2)}s): ${finding.message}`);
  for(const error of allErrors.filter(e=>e.includes(result.id))){
   if(!result.runtime_errors.includes(error))result.runtime_errors.push(error);
   if(!result.issues.includes(error))result.issues.push(error);
  }
 }
 console.log('OFFLINE_AUDIT_JSON:'+JSON.stringify({audit_version:2,shots:results,page_errors:pageErrors,
  limitation:'All-frame runtime checks and camera-compensated snapshot metrics cannot establish semantic relevance, contact or visual quality. Human review is still required.'}));
}catch(e){console.error('AUDIT FAILED:',e.message);process.exitCode=1}
finally{if(browser)await browser.close();await new Promise(r=>server.close(r))}
