// Audit-only instrumentation. Never loaded by the normal renderer.
export function inspectFigure(o, poses) {
  const issues = [];
  const p = o.pose ?? poses.stand;
  for (const key of Object.keys(poses.stand)) {
    if (!Array.isArray(p?.[key]) || p[key].length !== 2 || !p[key].every(Number.isFinite))
      issues.push(`Invalid rig joint ${key}: expected two finite numbers [x,y], not an object or world coordinates`);
  }
  for (const key of ['x','y']) if (!Number.isFinite(o[key])) issues.push(`Invalid figure ${key}`);
  if (!Number.isFinite(o.s ?? 1) || (o.s ?? 1) <= 0) issues.push('Invalid figure scale');
  if (issues.length) return issues;
  const segments = [['head','sh'],['sh','hip'],['sh','eF'],['eF','hF'],['sh','eB'],['eB','hB'],['hip','kF'],['kF','fF'],['hip','kB'],['kB','fB']];
  const length = (q,a,b) => Math.hypot(q[a][0]-q[b][0],q[a][1]-q[b][1]);
  for (const [a,b] of segments) {
    const lengths = Object.values(poses).map(q=>length(q,a,b));
    const value = length(p,a,b), upper = Math.max(...lengths)*1.35;
    // Pose blends can shorten bones; only flag extreme collapse, or elongation
    // beyond the entire shipped pose library plus a generous tolerance.
    const lower = a === 'head' || a === 'sh' && b === 'hip' ? Math.min(...lengths)*.45 : 2;
    if (value > upper || value < lower)
      issues.push(`Malformed rig segment ${a}-${b}: length ${value.toFixed(1)}; expected ${lower.toFixed(1)}–${upper.toFixed(1)} local units. Move connected joints together; use pose('sit') or reachable arm targets`);
  }
  return issues;
}

export function installCanvasAudit(scope) {
  const proto = scope.CanvasRenderingContext2D.prototype;
  const paths = new WeakMap();
  for (const method of ['beginPath','moveTo','lineTo','arc','fill']) {
    const original = proto[method];
    proto[method] = function(...args) {
      let state = paths.get(this) || {arcs:[],connected:false};
      if (method === 'beginPath') state = {arcs:[],connected:false};
      if (method === 'moveTo') state.connected=false;
      if (method === 'lineTo') state.connected=false;
      if (method === 'arc') {
        const [x,y,r,start,end] = args;
        if (Math.abs(end-start) >= Math.PI*2-.001) {
          const prev=state.arcs.at(-1);
          if (state.connected && prev && Math.hypot(x-prev[0],y-prev[1]) > (r+prev[2])*4)
            state.bridge=true;
          state.arcs.push([x,y,r]);state.connected=true;
        } else state.connected=false;
      }
      if (method === 'fill' && state.bridge && scope.__auditShot)
        scope.__auditFinding('Distant circles joined in one filled path: unintended connecting polygons. Use beginPath/fill per circle or moveTo before each arc');
      paths.set(this,state);
      return original.apply(this,args);
    };
  }
  const counts = {moveTo:2,lineTo:2,bezierCurveTo:6,quadraticCurveTo:4,arc:5,arcTo:5,ellipse:7,rect:4,fillRect:4,strokeRect:4,clearRect:4,translate:2,scale:2,rotate:1,transform:6};
  for (const [method,count] of Object.entries(counts)) {
    const original = proto[method];
    proto[method] = function(...args) {
      if (scope.__auditShot && args.slice(0,count).some(v=>!Number.isFinite(v)))
        scope.__auditFinding(`Invalid Canvas ${method} coordinates (NaN/undefined/infinite); drawing may silently disappear`);
      return original.apply(this,args);
    };
  }
}

export function instrumentModule(source, kind) {
  const signature = kind === 'rig' ? 'export function drawFigure(g, o) {' : 'export function registerShot(id, def) {';
  if (!source.includes(signature)) throw new Error('Unsupported engine signature for geometry audit: '+kind);
  if (kind === 'rig') return "import {inspectFigure} from '/__audit_geometry.mjs';\n" + source.replace(signature,
    signature + `
    if(globalThis.__auditFinding) {
      globalThis.__auditFigureSeen?.();
      if(JSON.stringify(POSES)!==__auditPoseJSON) globalThis.__auditFinding('Shared POSES mutated: deep-copy joint arrays before editing; accumulated edits make playback depend on render order');
      for(const issue of inspectFigure(o, __auditPoseBaseline)) globalThis.__auditFinding(issue);
    }`) + '\nconst __auditPoseJSON=JSON.stringify(POSES), __auditPoseBaseline=JSON.parse(__auditPoseJSON);\n';
  return source.replace(signature, signature + `
    const originalDraw = def.draw;
    if (originalDraw) def = {...def, draw(...args) {
      const previous = globalThis.__auditShot;
      globalThis.__auditShot = id;
      try { return originalDraw.apply(this,args); }
      finally { globalThis.__auditShot = previous; }
    }};`);
}
