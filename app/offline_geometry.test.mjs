import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectFigure,installCanvasAudit,instrumentModule} from './offline_geometry.mjs';
const stand={head:[3,-208],sh:[0,-174],hip:[0,-100],eF:[9,-137],hF:[13,-101],eB:[-7,-136],hB:[-9,-100],kF:[6,-50],fF:[3,0],kB:[-6,-50],fB:[-11,0]};
const poses={stand};
const figure=p=>({x:200,y:600,s:3,pose:p});
test('healthy rig is clear; detached head and stretched arms are flagged',()=>{
 assert.deepEqual(inspectFigure(figure(stand),poses),[]);
 assert.ok(inspectFigure(figure({...stand,sh:[0,-30]}),poses).some(x=>x.includes('head-sh')));
 assert.ok(inspectFigure(figure({...stand,hF:[190,-101]}),poses).some(x=>x.includes('eF-hF')));
});
test('object joints, NaN and invalid figure transforms cannot silently pass',()=>{
 for(const hF of [{x:10,y:20},{...stand.hF},[NaN,20],[1,Infinity]])
  assert.ok(inspectFigure(figure({...stand,hF}),poses).some(x=>x.includes('Invalid rig joint hF')));
 assert.ok(inspectFigure({...figure(stand),x:NaN},poses).length);
});
function canvas(){
 class Context {}
 for(const method of ['beginPath','moveTo','lineTo','arc','fill','bezierCurveTo','quadraticCurveTo','arcTo','ellipse','rect','fillRect','strokeRect','clearRect','translate','scale','rotate','transform'])Context.prototype[method]=()=>{};
 const findings=[];installCanvasAudit({CanvasRenderingContext2D:Context,__auditShot:'s005',__auditFinding:m=>findings.push(m)});
 return {g:new Context(),findings};
}
test('distant filled circles expose accidental hourglass polygons',()=>{
 const {g,findings}=canvas();g.beginPath();
 for(const [x,y] of [[10,10],[1000,10],[10,1800],[1000,1800]])g.arc(x,y,10,0,Math.PI*2);
 g.fill();assert.ok(findings.some(x=>x.includes('connecting polygons')));
});
test('separate circles and deliberate moveTo subpaths remain clear',()=>{
 const {g,findings}=canvas();g.beginPath();
 for(const x of [10,1000]){g.moveTo(x+10,20);g.arc(x,20,10,0,Math.PI*2)}g.fill();
 for(const x of [10,1000]){g.beginPath();g.arc(x,20,10,0,Math.PI*2);g.fill()}
 assert.deepEqual(findings,[]);
});
test('Canvas NaN drawing is reported even though the native API does not throw',()=>{
 const {g,findings}=canvas();g.lineTo(undefined,50);assert.ok(findings.some(x=>x.includes('Invalid Canvas')));
});
test('unsupported engine signature fails closed',()=>assert.throws(()=>instrumentModule('changed engine','rig'),/Unsupported/));
test('instrumented rig detects shared preset mutations',async()=>{
 const source=`export const POSES=${JSON.stringify(poses)}; export function drawFigure(g, o) {return o}`;
 const code=instrumentModule(source,'rig').replace("'/__audit_geometry.mjs'",JSON.stringify(new URL('./offline_geometry.mjs',import.meta.url).href));
 const rig=await import('data:text/javascript,'+encodeURIComponent(code));
 const findings=[];globalThis.__auditFinding=m=>findings.push(m);
 try{rig.POSES.stand.head[0]-=10;rig.drawFigure(null,figure(rig.POSES.stand));assert.ok(findings.some(x=>x.includes('Shared POSES mutated')))}
 finally{delete globalThis.__auditFinding}
});
