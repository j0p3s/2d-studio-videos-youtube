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
