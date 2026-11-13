import { E } from '/engine/core.js';
import { drawFigure, pose, blendPose, bigFace, armPose, jointWorld } from '/engine/rig2d.js';

const C={bg:'#101923',deep:'#080f16',wall:'#172b35',teal:'#51dfc2',gold:'#ffbd76',white:'#e9f3e9',muted:'#7b9caa',red:'#e88173'};
const clamp=x=>Math.max(0,Math.min(1,x));
const smooth=x=>{x=clamp(x);return x*x*(3-2*x)};
const lerp=(a,b,t)=>a+(b-a)*t;
// Reviewed habit scenes use these actions instead of arbitrary generated anatomy.
// All motion is derived from time; no persistent pose/path state is retained.
export function renderHabit(g,t,info,spec){
 const p=clamp(info.p);g.save();g.scale(E.W/1080,E.H/1920);
 room(g,t,true);tag(g,spec.title,spec.subtitle||'one small action');
 const kind=spec.kind;
 if(kind==='breathe'){
  const breath=spec.phase==='in'?smooth(p):spec.phase==='out'?1-smooth(p):.5-.5*Math.cos(p*Math.PI*2);
  let q=pose('stand');for(const k of ['head','sh','eF','hF','eB','hB'])q[k][1]-=7*breath;
  q=armPose(q,[12,-145-7*breath],'F');q=armPose(q,[-10,-113-5*breath],'B',-1);
  drawFigure(g,{x:385,y:1430,s:3.8,pose:q,expr:'neutral',blink:true,outfit:{top:'hoodie',color:'#228c80',legs:'#17242a'},rim:{color:C.gold,dir:[-1,-.4],w:3}});
  const r=100+65*breath;glow(g,790,880,260,'rgba(76,222,191,.10)');
  circle(g,790,880,r,'#153c40');g.strokeStyle=C.teal;g.lineWidth=5;g.stroke();
  txt(g,spec.phase==='in'?'INHALE':spec.phase==='out'?'EXHALE':p<.5?'INHALE':'EXHALE',790,1120,30,C.white,'center');
  txt(g,'SLOW DOWN',790,1170,22,C.muted,'center');
 }
 if(kind==='stretch'){
  const k=smooth(Math.min(1,p*1.7)),settle=Math.sin(t*1.1)*1.2;
  const q=blendPose('relaxed','cheer',k);
  for(const j of ['head','sh','eF','hF','eB','hB'])q[j]=[q[j][0]+settle,q[j][1]];
  figure(g,510,1440,3.65,q,'smile',t);
  // Faint trajectories show the shoulder-opening action; feet remain planted.
  g.globalAlpha=.3*k;line(g,[[210,850],[170,730],[190,610]],C.gold,5);line(g,[[810,850],[850,730],[830,610]],C.gold,5);g.globalAlpha=1;
  txt(g,'REACH • RELEASE',540,1510,29,C.teal,'center');
 }
 if(kind==='journal'){
  // The hand, pen tip and written path share one analytic trajectory.
  box(g,230,1120,140,280,'#182932',24);box(g,255,1390,24,60,'#3b5058',4);
  const tip=[475+48*smooth(p),1110+5*Math.sin(p*Math.PI*8)];
  const o={x:300,y:1440,s:4,pose:pose('sit'),expr:'determined',outfit:{top:'hoodie',color:'#228c80',legs:'#17242a'},rim:{color:C.gold,dir:[-1,-.4],w:3}};
  // Move the page within the arm's reach instead of stretching the arm to it.
  const desired=[(tip[0]-12-o.x)/o.s,(tip[1]-26-o.y)/o.s];
  o.pose=armPose(o.pose,desired,'F');
  o.pose=armPose(o.pose,[34,-93],'B');
  drawFigure(g,o);
  box(g,210,1140,810,35,'#826650',6);box(g,235,1175,28,265,'#26343b',2);box(g,965,1175,28,265,'#26343b',2);
  // Closed laptop reinforces writing before opening it.
  box(g,735,1104,240,33,'#344e58',8);line(g,[[750,1119],[960,1119]],'#779795',3);
  box(g,445,1080,260,58,'#dedac0',5);
  const h=jointWorld(o,'hF'),actual=[h[0]+12,h[1]+26];
  const pts=[];for(let i=0;i<=35;i++){const u=p*i/35;const target=[475+48*smooth(u),1110+5*Math.sin(u*Math.PI*8)];const f={...o,pose:armPose(pose('sit'),[(target[0]-12-o.x)/4,(target[1]-26-o.y)/4],'F')};const a=jointWorld(f,'hF');pts.push([a[0]+12,a[1]+26])}
  line(g,pts,'#40534c',3);line(g,[h,actual],C.gold,8);
  panel(g,565,570,390,265);txt(g,spec.gratitude?'I AM GRATEFUL FOR':'TODAY’S ONE GOAL',760,630,23,C.teal,'center');
  const labels=spec.gratitude?['A FRESH START','SOMEONE WHO CARES']:['ONE CLEAR OBJECTIVE'];
  labels.forEach((s,i)=>{g.globalAlpha=smooth(p*3-i*.6);txt(g,s,760,710+i*55,24,C.white,'center')});g.globalAlpha=1;
 }
 if(kind==='reset'){
  desk(g,t,p>.5,p);const k=smooth(p*1.8);box(g,lerp(450,115,k),1245,105,165,'#19313c',13);
  box(g,lerp(462,127,k),1260,81,110,k>.65?'#0b1921':'#ba936e',6);
  if(p>.5){g.globalAlpha=smooth((p-.5)*4);txt(g,'DISTRACTIONS OFF',735,560,29,C.teal,'center');g.globalAlpha=1}
 }
 if(kind==='steps'){
  const labels=spec.labels||['BREATHE','WRITE','STRETCH'];const gap=Math.min(265,900/labels.length);
  labels.forEach((label,i)=>{const k=smooth(p*labels.length-i),y=425+i*gap;panel(g,120,y,840,gap-30);box(g,160,y+38,54,54,'#0c212b',10);if(k>0)check(g,169,y+65,k,33);txt(g,label,265,y+65,35,k>.7?C.white:C.muted);box(g,265,y+108,620*k,7,C.teal,3)});
 }
 if(kind==='calendar'){
  panel(g,130,405,820,800);txt(g,'TOMORROW',540,485,48,C.white,'center');
  const labels=spec.labels||['BREATHE','ONE CLEAR GOAL','STRETCH'];
  labels.forEach((s,i)=>{const y=635+i*170,k=smooth(p*3-i*.5);circle(g,230,y,33,'#12363a');if(k>0)check(g,212,y,k,34);txt(g,s,310,y,34);line(g,[[310,y+55],[840,y+55]],'#35515b',2)});
  const hi=Math.min(2.999,p*3),hy=635+Math.floor(hi)*170;g.save();g.globalAlpha=.22+.12*Math.sin(t*4);box(g,150,hy-62,780,124,C.teal,18);g.restore();
  const sy=1330-smooth(p)*150,sr=70+smooth(p)*40+Math.sin(t*2)*6;glow(g,540,sy,sr*3,'rgba(255,205,110,.30)');circle(g,540,sy,sr,C.gold);
  txt(g,'SMALL ENOUGH TO REPEAT',540,1400,32,C.gold,'center');
 }
 if(kind==='hero'){
  const q=blendPose('relaxed','point',smooth(p*1.8));figure(g,300,1430,3.8,q,'smile',t);
  panel(g,600,710,355,480);txt(g,'START',777,805,45,C.teal,'center');txt(g,'SMALL',777,875,45,C.white,'center');
  check(g,725,1000,smooth(p*2),85);txt(g,'REPEAT TOMORROW',777,1110,21,C.gold,'center');
 }
 atmosphere(g,t);g.restore();
}
function box(g,x,y,w,h,fill,r=16){g.fillStyle=fill;g.beginPath();g.roundRect(x,y,w,h,r);g.fill()}
function line(g,pts,color,width=5){g.strokeStyle=color;g.lineWidth=width;g.lineCap='round';g.lineJoin='round';g.beginPath();pts.forEach(([x,y],i)=>i?g.lineTo(x,y):g.moveTo(x,y));g.stroke()}
function circle(g,x,y,r,color){g.fillStyle=color;g.beginPath();g.arc(x,y,r,0,Math.PI*2);g.fill()}
function txt(g,s,x,y,size=40,color=C.white,align='left'){g.fillStyle=color;g.font=`800 ${size}px Nunito, sans-serif`;g.textAlign=align;g.textBaseline='middle';g.fillText(s,x,y)}
function glow(g,x,y,r,color){let a=g.createRadialGradient(x,y,0,x,y,r);a.addColorStop(0,color);a.addColorStop(1,'rgba(0,0,0,0)');g.fillStyle=a;g.fillRect(x-r,y-r,2*r,2*r)}
function panel(g,x,y,w,h){box(g,x+10,y+17,w,h,'#060c12');box(g,x,y,w,h,'#1a303c');g.strokeStyle='#34515c';g.lineWidth=2;g.stroke()}
function tag(g,label,sub){txt(g,sub.toUpperCase(),90,165,26,C.teal);txt(g,label,90,225,54)}
function atmosphere(g,t){for(let i=0;i<22;i++){let x=(i*179+Math.sin(t*.16+i)*35)%1080,y=(i*109-t*9+2400)%1500;circle(g,x,y,1.5,'rgba(244,208,150,.18)')}}
function room(g,t,warm=false){
 let gr=g.createLinearGradient(0,0,1080,1600);gr.addColorStop(0,C.bg);gr.addColorStop(1,warm?'#27332f':'#101f2b');g.fillStyle=gr;g.fillRect(0,0,1080,1920);
 box(g,75,340,430,600,'#09131e',3);let sky=g.createLinearGradient(0,350,0,930);sky.addColorStop(0,'#244a60');sky.addColorStop(1,warm?'#edb17d':'#5c8e91');g.fillStyle=sky;g.fillRect(90,355,400,565);
 for(let i=0;i<7;i++)box(g,100+i*58,820-((i*41)%170),45,140+((i*41)%170),'#203941',0);
 line(g,[[290,350],[290,930]],'#122530',16);line(g,[[85,650],[500,650]],'#122530',16);
 g.fillStyle=warm?'rgba(255,196,125,.055)':'rgba(126,222,206,.035)';g.beginPath();g.moveTo(490,650);g.lineTo(1060,1470);g.lineTo(350,1470);g.closePath();g.fill();
 box(g,0,1420,1080,500,'#0b151c',0);line(g,[[0,1420],[1080,1420]],'#2c4148',3);
 box(g,870,400,120,24,'#34464b',3);box(g,870,680,120,24,'#34464b',3);
 for(let i=0;i<4;i++)box(g,880+i*22,565-i*10,13,115+i*10,i%2? '#385b5b':'#6b6050',2);
 atmosphere(g,t);
}
function figure(g,x,y,s,p,expr='determined',t=0){drawFigure(g,{x,y,s,pose:p,expr,outfit:{top:'hoodie',color:'#228c80',legs:'#17242a'},rim:{color:C.gold,dir:[-1,-.4],w:3},blink:Math.sin(t*.7)>0.997?1:0})}
function seatPose(t,working){let p={...pose('stand'),head:[8,-208],sh:[0,-172],hip:[-12,-100],kF:[38,-93],fF:[45,-12],kB:[15,-90],fB:[18,-9],eF:[35,-130],hF:[75,-115],eB:[30,-143],hB:[70,-117]};
 if(working){p.hF=[75,-115-Math.max(0,Math.sin(t*13))*4];p.hB=[68,-119-Math.max(0,Math.sin(t*13+2))*4];p.head=[10+Math.sin(t*2),-208]}
 else{p.head=[22,-193];p.eF=[35,-164];p.hF=[35,-193];p.eB=[20,-125];p.hB=[65,-115]}
 return p}
function desk(g,t,working,p=.5){
 box(g,265,1090,95,260,'#17232b',22);box(g,290,1340,35,110,'#33424a',6);line(g,[[245,1450],[390,1450]],'#33424a',12);
 figure(g,330,1430,3.05,seatPose(t,working),working?'determined':'worried',t);
 // Screen sits on the desk, keyboard is at the wrists.
 box(g,660,855,310,225,'#070e14',15);box(g,675,870,280,185,'#183a43',8);glow(g,780,940,230,'rgba(62,233,193,.12)');
 for(let i=0;i<4;i++){box(g,700,910+i*30,working?60+150*clamp(p+i*.11):120,7,i===0?C.teal:'#53817f',3)}
 box(g,790,1078,18,65,'#46575c',3);box(g,745,1137,110,10,'#4a6267',3);
 box(g,225,1135,820,36,'#826650',5);box(g,240,1171,790,15,'#302d28',2);box(g,270,1180,28,260,'#232d31',2);box(g,968,1180,28,260,'#232d31',2);
 box(g,485,1112,145,15,'#3b5459',3);for(let i=0;i<9;i++)line(g,[[496+i*14,1114],[496+i*14,1123]],'#9aaba9',2);
 // Empty floor, captions remain below the action.
}
function check(g,x,y,k,size=46){line(g,[[x,y],[x+size*.3*k,y+size*.3*k],[x+size*k,y-size*.5*k]],C.teal,8)}
function phone(g,x,y,p){panel(g,x,y,290,490);box(g,x+20,y+25,250,430,'#10272e',15);txt(g,'FOCUS',x+145,y+90,28,C.teal,'center');txt(g,'05:00',x+145,y+220,65,C.white,'center');circle(g,x+145,y+340,47,C.teal);g.fillStyle=C.deep;g.beginPath();g.moveTo(x+134,y+320);g.lineTo(x+134,y+360);g.lineTo(x+164,y+340);g.fill();}
function timer(g,t,p,end=false){
 tag(g,end?'SPRINT COMPLETE':'JUST FIVE MINUTES',end?'one small win':'make starting easy');
 let x=540,y=835,r=320;glow(g,x,y,560,'rgba(66,226,184,.10)');circle(g,x,y,r+22,'#1b3842');circle(g,x,y,r,'#0d1d27');
 for(let i=0;i<60;i++){let a=i*Math.PI/30-Math.PI/2;line(g,[[x+Math.cos(a)*290,y+Math.sin(a)*290],[x+Math.cos(a)*(i%5?280:265),y+Math.sin(a)*(i%5?280:265)]],i%5?'#38545c':C.gold,i%5?3:5)}
 g.strokeStyle=C.teal;g.lineWidth=14;g.lineCap='round';g.beginPath();g.arc(x,y,310,-Math.PI/2,-Math.PI/2+Math.PI*2*(end?1:Math.max(.02,p)));g.stroke();
 txt(g,end?'00:00':'05:00',540,815,112,C.white,'center');txt(g,end?'DONE':'MORNING SPRINT',540,920,28,C.teal,'center');
 if(end){check(g,510,1060,smooth(p*3),52);for(let i=0;i<18;i++){let a=i*2.4;circle(g,540+Math.cos(a)*(310+120*p),835+Math.sin(a)*(310+120*p),4,C.gold)}}
 else{let tap=Math.sin(Math.PI*smooth(p));g.save();g.translate(790-150*tap,1290-120*tap);g.rotate(-.3);line(g,[[0,120],[0,10]],'#050b12',75);line(g,[[0,10],[0,-90]],C.gold,52);g.restore()}
}
function tasks(g,t,p,mode){
 tag(g,mode==='calendar'?'THE DEADLINE MOVES CLOSER':'ONE TASK BECOMES MOMENTUM',mode==='calendar'?'less room to drift':'start → finish → repeat');
 const labels=mode==='calendar'?['MON','TUE','WED','THU','FRI']:['START THE TASK','FINISH ONE THING','KEEP GOING'];
 labels.forEach((label,i)=>{let done=smooth((p-i*.16)*3),y=410+i*(mode==='calendar'?165:265);panel(g,100+Math.sin(i+t*.3)*3,y,880,mode==='calendar'?135:210);box(g,140,y+45,48,48,'#10262e',8);if(done>.05)check(g,149,y+70,done,29);txt(g,label,220,y+70,mode==='calendar'?38:40,done>.7?C.white:C.muted);if(mode!=='calendar')box(g,225,y+130,650*done,9,C.teal,4);if(mode==='calendar'&&i===4)txt(g,'DUE',845,y+70,30,C.gold,'center')});
}
function diagram(g,t,p,brain=false){
 tag(g,brain?'A CLEAR SIGNAL: FINISHED':'STARTING CREATES MOMENTUM',brain?'a rewarding finish':'the effort gets easier');
 let nodes=brain?[[540,500],[310,730],[750,730],[350,1000],[720,1000],[540,1220]]:[[260,1160],[530,870],[800,570]];
 nodes.forEach((v,i)=>{if(i){let prev=nodes[Math.max(0,i-1)];line(g,[prev,v],'#294d58',6);let k=(t*.5+i*.15)%1;circle(g,lerp(prev[0],v[0],k),lerp(prev[1],v[1],k),10,C.teal)}glow(g,v[0],v[1],100,'rgba(67,227,191,.12)');circle(g,v[0],v[1],brain?45:68,C.deep);g.strokeStyle=C.teal;g.lineWidth=4;g.stroke();if(!brain)txt(g,['START','MOVE','FLOW'][i],v[0],v[1]+125,34,C.white,'center')});
 if(brain){txt(g,'TASK COMPLETE',540,1370,35,C.gold,'center');circle(g,540,500,20+Math.sin(t*3)*5,C.gold)}
 else{line(g,[[150,1350],[930,1350]],C.muted,3);txt(g,'EFFORT',150,1410,25,C.muted);txt(g,'PROGRESS',930,1410,25,C.teal,'right')}
}
export function renderStory(g,t,info,n){
 const p=clamp(info.p),W=E.W,H=E.H;g.save();g.scale(W/1080,H/1920);
 room(g,t,n>7);
 // Modest camera drift, centered away from the caption safe area.
 g.save();let z=1+.025*smooth(p);g.translate(540,900);g.scale(z,z);g.translate(-540,-900);
 if(n===1){tag(g,'STUCK IN THE LOOP?','another morning, same distraction');desk(g,t,false);let a=t*1.4;for(let i=0;i<3;i++){let x=710+Math.cos(a+i*2.1)*150,y=580+Math.sin(a+i*2.1)*120;box(g,x-62,y-42,124,84,'#3c3637',14);txt(g,['LATER','SCROLL','WAIT'][i],x,y,20,C.gold,'center')}}
 if(n===2){tag(g,'BREAK THE CYCLE','change the first move');let k=smooth(p*2);desk(g,t,k>.5,p);let x=lerp(470,170,k);box(g,x,1250,110,175,'#1b3440',15);box(g,x+12,1268,86,126,k>.6?'#101b24':'#b28b66',8);if(k>.6){check(g,760,650,smooth((p-.4)*3),75)}}
 if(n===3){tag(g,'A SMALL DAILY RITUAL','the same place, a new choice');desk(g,t,true,p);let k=smooth(p*2);g.globalAlpha=k;box(g,105,360,750,115,'#1b393f',14);txt(g,'ONE TASK. FIVE MINUTES.',480,418,39,C.white,'center');g.globalAlpha=1}
 if(n===4||n===5||n===12)timer(g,t,p,n===12);
 if(n===6){tag(g,'OPEN THE TASK. START.','before the distractions');desk(g,t,true,p);box(g,610,435,355,165,'#163b3d',15);txt(g,'FIRST TASK',787,490,29,C.teal,'center');txt(g,'IN PROGRESS',787,550,31,C.white,'center');let k=smooth(p);box(g,650,615,270*k,8,C.teal,3)}
 if(n===7){tag(g,'A BRIEF, FOCUSED BURST','a simple way to begin');panel(g,105,410,870,760);for(let i=0;i<12;i++){line(g,[[150,475+i*52],[930,475+i*52]],'#233e49',1)}line(g,[[210,1050],[210,560]],C.muted,3);line(g,[[210,1050],[870,1050]],C.muted,3);let pts=[];for(let i=0;i<=50;i++){let u=i/50*smooth(p);pts.push([210+650*u,1040-430*(1-Math.exp(-3*u))])}if(pts.length)line(g,pts,C.teal,9);txt(g,'START',240,1120,25,C.gold);txt(g,'MOMENTUM',800,1120,25,C.teal,'center')}
 if(n===8)diagram(g,t,p);
 if(n===9)tasks(g,t,p,'tasks');
 if(n===10)tasks(g,t,p,'calendar');
 if(n===11){tag(g,'AND THE TWIST?','the finish changes the next move');glow(g,540,800,650,'rgba(255,187,111,.12)');bigFace(g,540,810,270,{expr:p<.35?'thinking':'surprised',rimColor:C.gold,look:[0,-.2],blink:0});for(let i=0;i<3;i++)line(g,[[790+i*40,410+i*50],[825+i*40,370+i*50]],C.gold,8)}
 if(n===13)diagram(g,t,p,true);
 if(n===14){tag(g,'STAY WITH THE WORK','protect the next hour');desk(g,t,true,p);let x=170;box(g,x,1270,105,170,'#14212a',12);txt(g,'Z',x+52,1350,35,C.muted,'center');box(g,600,490,340,105,'#1a3c3c',14);txt(g,'FOCUS MODE',770,540,30,C.teal,'center');let a=t*.9;circle(g,900,435,12,C.teal)}
 if(n===15){tag(g,'START YOUR FIVE MINUTES','one small win. then another.');let k=smooth(p*1.5);figure(g,330,1430,3.55,blendPose('relaxed','point',k),'smile',t);phone(g,640,715,p);let pts=[[120,560],[350,520],[530,430],[775,335]];line(g,pts,'#28484b',8);let marker=clamp(p)*3,idx=Math.min(2,Math.floor(marker)),f=marker-idx;circle(g,lerp(pts[idx][0],pts[idx+1][0],f),lerp(pts[idx][1],pts[idx+1][1],f),13,C.teal);if(p>.65){g.globalAlpha=smooth((p-.65)*4);txt(g,'START TODAY',540,1490,41,C.gold,'center');g.globalAlpha=1}}
 g.restore();atmosphere(g,t);g.restore();
}
