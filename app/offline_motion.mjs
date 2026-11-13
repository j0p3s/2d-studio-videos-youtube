// Align sparse frames before measuring residual changes. This reduces (but does
// not eliminate) camera drift/zoom masquerading as character motion.
export function motionMetrics(a,b,size=32){
 const compare=(dx,dy,scale)=>{
  let changed=0,count=0;const center=(size-1)/2;
  for(let y=2;y<size-2;y++)for(let x=2;x<size-2;x++){
   const bx=Math.round(center+(x-center)*scale+dx),by=Math.round(center+(y-center)*scale+dy);
   if(bx<0||by<0||bx>=size||by>=size)continue;
   const i=(y*size+x)*3,j=(by*size+bx)*3;
   if(Math.max(Math.abs(a[i]-b[j]),Math.abs(a[i+1]-b[j+1]),Math.abs(a[i+2]-b[j+2]))>18)changed++;
   count++;
  }
  return count?changed/count:0;
 };
 const raw=compare(0,0,1);let residual=raw;
 for(const scale of [.94,.97,1,1.03,1.06])for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){
  residual=Math.min(residual,compare(dx,dy,scale));
 }
 return {raw,residual};
}
