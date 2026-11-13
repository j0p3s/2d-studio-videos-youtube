import test from 'node:test';
import assert from 'node:assert/strict';
import {motionMetrics} from './offline_motion.mjs';
function frame(dx=0,localMove=0){
 const a=[];
 for(let y=0;y<32;y++)for(let x=0;x<32;x++){
  const xx=x-dx;
  const fixed=(xx>5&&xx<10&&y>6&&y<25)||(xx>22&&xx<27&&y>5&&y<20);
  const actor=xx>12+localMove&&xx<18+localMove&&y>12&&y<24;
  a.push(fixed?130:actor?240:10,fixed?170:actor?100:20,fixed?190:actor?60:30);
 }
 return a;
}
test('pure camera translation does not count as character motion',()=>{
 const r=motionMetrics(frame(),frame(1));
 assert.ok(r.raw>.008);assert.equal(r.residual,0);
});
test('independent character action remains after camera alignment',()=>{
 const r=motionMetrics(frame(),frame(1,3));
 assert.ok(r.residual>.008);
});
test('static frames have no motion',()=>{
 assert.deepEqual(motionMetrics(frame(),frame()),{raw:0,residual:0});
});
