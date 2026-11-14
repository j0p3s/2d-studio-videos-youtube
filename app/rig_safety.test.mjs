import test from 'node:test';
import assert from 'node:assert/strict';
import {JOINTS,clonePose,armPose,jointWorld} from './rig_safety.mjs';
const pose=()=>Object.fromEntries(JOINTS.map((key,i)=>[key,[i,i*2]]));

test('copying poses never aliases preset joint arrays',()=>{
 const original=pose(),copy=clonePose(original);copy.head[0]=999;
 assert.equal(original.head[0],0);
 for(const key of JOINTS)assert.notEqual(original[key],copy[key]);
});
test('unreachable and zero-distance arm targets preserve finite fixed bone lengths',()=>{
 const original=pose();
 for(const target of [[10000,-2000],original.sh]){
  const q=armPose(original,target);
  assert.ok(Math.abs(Math.hypot(q.eF[0]-q.sh[0],q.eF[1]-q.sh[1])-38)<1e-6);
  assert.ok(Math.abs(Math.hypot(q.hF[0]-q.eF[0],q.hF[1]-q.eF[1])-38)<1e-6);
  assert.ok(q.hF.every(Number.isFinite));
 }
 assert.deepEqual(original,pose());
 assert.throws(()=>armPose(original,[0,0],'F',NaN),/Invalid arm/);
});
test('world joints use the renderer mirror, child scale and hip rotation order',()=>{
 const p=pose();p.hip=[2,3];p.hF=[4,3];
 const result=jointWorld({x:100,y:200,s:2,facing:-1,rot:Math.PI/2,outfit:{kid:true},pose:p},'hF');
 assert.ok(Math.abs(result[0]-(100-2*1.44))<1e-6);
 assert.ok(Math.abs(result[1]-(200+5*1.44))<1e-6);
 assert.throws(()=>jointWorld({x:NaN,y:0,pose:p},'hF'),/Non-finite/);
});

import {restOn,surfaceGap,figureLowest} from './rig_safety.mjs';
const STAND={head:[3,-208],sh:[0,-174],hip:[0,-100],eF:[9,-137],hF:[13,-101],eB:[-7,-136],hB:[-9,-100],kF:[6,-50],fF:[3,0],kB:[-6,-50],fB:[-11,0]};
const lying=(y)=>({x:500,y,s:2.4,facing:1,rot:Math.PI/2,pose:STAND});

test('restOn puts a lying figure on the surface instead of floating at the feet position',()=>{
 const surface=900,naive=lying(surface),y=restOn(naive,surface);
 assert.ok(surfaceGap(naive,surface)>0,'a figure rotated around the hip floats when y is the surface');
 assert.ok(Math.abs(surfaceGap({...naive,y},surface))<1e-6);
 assert.equal(figureLowest({...naive,y})<=surface+1e-6,true);
});

test('restOn keeps a standing figure with its feet on the surface',()=>{
 const o={x:0,y:0,s:1,facing:1,pose:STAND},y=restOn(o,500);
 assert.ok(Math.abs(surfaceGap({...o,y},500))<1e-6);
});

test('restOn rejects non-finite input like the rest of the rig helpers',()=>{
 assert.throws(()=>restOn({x:NaN,y:0,pose:pose()},10),TypeError);
});
