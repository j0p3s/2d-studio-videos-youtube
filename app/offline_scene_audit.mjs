// Local-only multi-frame audit against the same player used by the studio.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {createRequire} from 'node:module';
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
  if(url==='/__manifest'){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify(manifest(path.join(project,'scenes'),'/project/scenes')))}
  const root=url.startsWith('/project/')?project:studio;
  const p=path.resolve(root,url.startsWith('/project/')?url.slice(9):'.'+url);
  if(!within(root,p)||!fs.existsSync(p)||!fs.statSync(p).isFile()){res.writeHead(404);return res.end()}
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
  for(const fraction of [.12,.5,.88]){
   const time=shot.start+(shot.end-shot.start)*fraction;
   const sample=await page.evaluate(({frame})=>{
    window.renderFrame(frame);
    const c=document.querySelector('#main'),ctx=c.getContext('2d');
    const data=ctx.getImageData(0,0,c.width,c.height).data;
    const pixels=[];for(let y=0;y<32;y++)for(let x=0;x<32;x++){
     const px=Math.floor((.08+.84*x/31)*(c.width-1));
     const py=Math.floor((.24+.49*y/31)*(c.height-1));
     const i=(py*c.width+px)*4;pixels.push(data[i],data[i+1],data[i+2]);
    }
    return {pixels,errors:[...window.ERRORS]};
   },{frame:Math.round(time*fps)});
   const image=path.join(folder,`${shot.id}_${fraction}.png`);await page.screenshot({path:image});
   samples.push({...sample,time,image});
  }
  const diff=(a,b)=>{let changed=0;for(let i=0;i<a.length;i+=3)if(Math.max(Math.abs(a[i]-b[i]),Math.abs(a[i+1]-b[i+1]),Math.abs(a[i+2]-b[i+2]))>18)changed++;return changed/(a.length/3)};
  const motion=Math.max(diff(samples[0].pixels,samples[1].pixels),diff(samples[1].pixels,samples[2].pixels));
  const pixels=samples[1].pixels;let mean=pixels.reduce((a,b)=>a+b,0)/pixels.length;
  const spread=Math.sqrt(pixels.reduce((a,b)=>a+(b-mean)**2,0)/pixels.length);
  const errors=[...new Set(samples.flatMap(s=>s.errors).filter(e=>e.includes(shot.id)))];
  const issues=[];if(!shot.ok)issues.push('Missing scene module');if(errors.length)issues.push(...errors);
  if(motion<.008)issues.push('Very little visible change in action area across three sampled moments');
  if(spread<9)issues.push('Action area is nearly uniform; subject or scene detail may be absent');
  results.push({id:shot.id,motion_ratio:+motion.toFixed(4),color_spread:+spread.toFixed(2),issues,
   runtime_errors:errors,missing:!shot.ok,images:samples.map(s=>s.image)});
 }
 console.log('OFFLINE_AUDIT_JSON:'+JSON.stringify({shots:results,page_errors:pageErrors,
  limitation:'Sampled runtime and pixel checks cannot establish semantic relevance or visual quality. Camera movement may pass motion checks without character action.'}));
}catch(e){console.error('AUDIT FAILED:',e.message);process.exitCode=1}
finally{if(browser)await browser.close();await new Promise(r=>server.close(r))}
