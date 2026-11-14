// Shared, deterministic rig math. No DOM or renderer dependencies.
import {isRigPose, rigJoints, rigReach, rigPose} from './skeleton.mjs';
export const JOINTS=['head','sh','hip','eF','hF','eB','hB','kF','fF','kB','fB'];
export function assertPose(p) {
 for(const k of JOINTS)if(!Array.isArray(p?.[k])||p[k].length!==2||!p[k].every(Number.isFinite))
  throw new TypeError(`Rig joint ${k} must be a finite [x,y] array`);
 return p;
}
export function clonePose(p){if(isRigPose(p))return rigPose(p);assertPose(p);return Object.fromEntries(JOINTS.map(k=>[k,[...p[k]]]));}
export function armPose(p,target,side='F',bend=1) {
 if(isRigPose(p)){if(Math.abs(bend)!==1)throw new TypeError('Invalid arm target');return rigReach(p,side,target)}
 const q=clonePose(p), shoulder=q.sh;
 if(!['F','B'].includes(side)||!Array.isArray(target)||!target.every(Number.isFinite)||target.length!==2||Math.abs(bend)!==1)throw new TypeError('Invalid arm target');
 const a=38,b=38,dx=target[0]-shoulder[0],dy=target[1]-shoulder[1];
 const raw=Math.hypot(dx,dy),d=Math.max(.001,Math.min(a+b-.001,raw));
 const direction=raw<.001?Math.PI/2:Math.atan2(dy,dx);
 const offset=Math.acos(Math.max(-1,Math.min(1,(a*a+d*d-b*b)/(2*a*d))));
 q['e'+side]=[shoulder[0]+a*Math.cos(direction-bend*offset),shoulder[1]+a*Math.sin(direction-bend*offset)];
 q['h'+side]=[shoulder[0]+d*Math.cos(direction),shoulder[1]+d*Math.sin(direction)];
 return q;
}
export function jointWorld(o,key) {
 const p=assertPose(isRigPose(o.pose)?rigJoints(o.pose,{build:o.build}):o.pose);if(!JOINTS.includes(key))throw new TypeError('Unknown joint '+key);
 if(![o.x,o.y,o.s??1,o.facing??1,o.rot??0].every(Number.isFinite))throw new TypeError('Non-finite figure transform');
 let [x,y]=p[key];const s=(o.s??1)*(o.outfit?.kid ? .72 : 1),f=o.facing??1;
 if(o.rot){const [hx,hy]=p.hip,c=Math.cos(o.rot),n=Math.sin(o.rot);[x,y]=[hx+(x-hx)*c-(y-hy)*n,hy+(x-hx)*n+(y-hy)*c]}
 return [o.x+x*f*s,o.y+y*s];
}

// Lowest drawn point of a figure in canvas coordinates (y grows downward). drawFigure rotates a figure
// around its HIP, so with `rot` set the feet are no longer the reference: a body lying on a bed ends up
// far above `y`. These helpers place or check a figure by where its body really is.
export function figureLowest(o,pad) {
 const s=(o.s??1)*(o.outfit?.kid ? .72 : 1),lying=Boolean(o.rot);
 const limb=pad??(lying ? 8 : 0);let low=-Infinity;
 for(const key of JOINTS){const y=jointWorld(o,key)[1];low=Math.max(low,y+(key==='head'&&lying ? 26 : limb)*s)}
 return low;
}
// y to pass to drawFigure so the body just touches a surface (a mattress top, the floor, a sofa seat).
export function restOn(o,surfaceY,pad) { return o.y+(surfaceY-figureLowest(o,pad)); }
// Positive: the figure floats this many units above the surface. Negative: it sinks into it.
export function surfaceGap(o,surfaceY,pad) { return surfaceY-figureLowest(o,pad); }
