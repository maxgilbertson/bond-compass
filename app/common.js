"use strict";
// Shared helpers for Bond Compass: formatting, navigation, the detail panel, charts and the live data loop.
// build_static.py flips STATIC to true for the GitHub Pages copy, which reads data files that GitHub Actions
// regenerates every ~15 minutes instead of calling the local server.
const STATIC = false;
const SITE_VERSION = "dev";  // build_static.py stamps each published build, so open pages can tell when a newer one is live
const REFRESH_MS = 5*60*1000;

/* ---------------------------------------------------------------- basics */
const makeStore = ns => ({get(k,d){try{const v=localStorage.getItem(ns+k);return v==null?d:JSON.parse(v)}catch(e){return d}},
                          set(k,v){try{localStorage.setItem(ns+k,JSON.stringify(v))}catch(e){}}});
const $ = s => document.querySelector(s);
const esc = s => String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const isNum = v => v!=null && !isNaN(v);
// fractions shown as percentages (returns)
const pct = (v,dp=1,sign=true) => !isNum(v) ? "–" : (sign&&v>0?"+":"")+(v*100).toFixed(dp)+"%";
// values already in % (yields, rates, ratios)
const yld = (v,dp=2) => !isNum(v) ? "–" : v.toFixed(dp)+"%";
const pp = (v,dp=1,sign=false) => !isNum(v) ? "–" : (sign&&v>0?"+":"")+v.toFixed(dp)+"%";
// basis points (0.01%)
const bpf = (v,sign=true,unit=true) => !isNum(v) ? "–" : (sign&&Math.round(v)>0?"+":"")+Math.round(v)+(unit?"bp":"");
const num = (v,dp=2) => !isNum(v) ? "–" : v.toLocaleString(undefined,{minimumFractionDigits:dp,maximumFractionDigits:dp});
const cls = v => !isNum(v)?"":v>0?"pos":v<0?"neg":"";
// a rise in yield is a fall in price: colour yield changes by what they do to a bond holder
const ycls = v => !isNum(v)||Math.abs(v)<0.5?"":v>0?"neg":"pos";
const sgnN = v => !isNum(v)? "–" : (Math.round(v)>0?"+":"")+Math.round(v);
function scoreColor(s){ return s>=60?"var(--pos)":s>=40?"var(--faint)":"var(--neg)"; }
function sigClass(sig){ return {"Strong overweight":"s-so","Overweight":"s-ow","Neutral":"s-ne","Underweight":"s-uw","Avoid":"s-av"}[sig]||"s-ne"; }
function ago(ms){ const s=Math.round((Date.now()-ms)/1000); if(s<60) return "just now"; const m=Math.round(s/60); return m<60?`${m} min ago`:m<2880?`${Math.round(m/60)} h ago`:`${Math.round(m/1440)} days ago`; }
const dateStr = (ts,year=true) => !ts? "–" : new Date(ts*1000).toLocaleDateString(undefined,{day:"numeric",month:"short",...(year?{year:"numeric"}:{}),timeZone:"UTC"});
const isoDate = (iso,year=true) => !iso? "–" : new Date(iso+"T12:00:00Z").toLocaleDateString(undefined,{day:"numeric",month:"short",...(year?{year:"numeric"}:{})});
const cap = s => s? s[0].toUpperCase()+s.slice(1) : s;
const tenorWord = t => t? (t.endsWith("M")? `${t.slice(0,-1)}-month` : `${t.slice(0,-1)}-year`) : "";
const tenorYears = t => t.endsWith("M")? +t.slice(0,-1)/12 : +t.slice(0,-1);

/* Diverging fill: blue = better for a bond holder (or below the middle), red = worse, grey in the middle. */
function divColor(v,center,capv,invert=false){ if(!isNum(v)) return "var(--surface2)";
  let t=Math.max(-1,Math.min(1,(v-center)/capv)); if(invert) t=-t;
  return `color-mix(in oklab,var(${t>=0?"--dpos":"--dneg"}) ${Math.round(8+Math.abs(t)*70)}%,var(--dmid))`; }
/* Sequential fill: one hue (blue), light to dark with the value. */
function seqColor(v,lo,hi){ if(!isNum(v)) return "var(--surface2)"; const t=Math.max(0,Math.min(1,(v-lo)/((hi-lo)||1)));
  return `color-mix(in oklab,var(--s1) ${Math.round(8+t*80)}%,var(--dmid))`; }

/* ---------------------------------------------------------------- signals */
const SIGNAL_HELP = {
  "Strong overweight":"Score 80 or more: these bonds rank near the top on value and on the safety of the government behind them.",
  "Overweight":"Score 60–79: the numbers favour holding more of these bonds than usual.",
  "Neutral":"Score 40–59: no clear edge either way.",
  "Underweight":"Score 20–39: the numbers suggest holding less of these than usual.",
  "Avoid":"Score under 20: among the weakest on value and safety together."};
function sigPill(sig,text=sig){ return `<span class="pill ${sigClass(sig)}" title="${esc(SIGNAL_HELP[sig]||"")}">${esc(text??"–")}</span>`; }
const SIG_ORDER = ["Strong overweight","Overweight","Neutral","Underweight","Avoid"];
const SIG_FILL = {"Strong overweight":"var(--pos)","Overweight":"color-mix(in oklab,var(--pos) 50%,var(--surface2))",
  "Neutral":"color-mix(in oklab,var(--faint) 55%,var(--surface2))","Underweight":"color-mix(in oklab,var(--neg) 50%,var(--surface2))","Avoid":"var(--neg)"};
function sigDist(sigs){
  const n=sigs.length, c=Object.fromEntries(SIG_ORDER.map(k=>[k,sigs.filter(s=>s===k).length]));
  return `<div class="sigbar" role="img" aria-label="${esc(SIG_ORDER.map(k=>`${k} ${c[k]}`).join(", "))}">${SIG_ORDER.filter(k=>c[k]).map(k=>`<i style="flex:${c[k]};background:${SIG_FILL[k]}" title="${esc(`${k}: ${c[k]} of ${n}`)}"></i>`).join("")}</div>
    <div class="siglegend">${SIG_ORDER.map(k=>`<span title="${esc(SIGNAL_HELP[k]||"")}"><i class="sw" style="background:${SIG_FILL[k]}"></i>${esc(k)}<b>${c[k]}</b></span>`).join("")}</div>`;
}
function ring(score,{size=46,stroke=5,color}={}){
  const r=(size-stroke)/2, c=2*Math.PI*r, v=score==null?0:Math.max(0,Math.min(100,score)), mid=size/2, col=color||(score==null?"var(--line)":scoreColor(score));
  return `<svg class="ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${score==null?"not available":Math.round(score)+" out of 100"}">
    <circle cx="${mid}" cy="${mid}" r="${r}" fill="none" stroke="color-mix(in oklab,${col} 18%,var(--surface2))" stroke-width="${stroke}"/>
    ${v?`<circle cx="${mid}" cy="${mid}" r="${r}" fill="none" stroke="${col}" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${(c*v/100).toFixed(2)} ${c.toFixed(2)}" transform="rotate(-90 ${mid} ${mid})"/>`:""}
    <text x="${mid}" y="${mid}" text-anchor="middle" dominant-baseline="central" font-size="${Math.round(size*.36)}" fill="var(--ink)">${score==null?"–":Math.round(score)}</text></svg>`;
}
const meter = (f,col="var(--pos)") => `<div class="meter" style="background:color-mix(in oklab,${col} 16%,var(--surface2))"><i style="width:${Math.round(Math.max(0,Math.min(1,f||0))*100)}%;background:${col}"></i></div>`;
// where today's value sits between a low and a high (with an optional average tick)
function rangeBar(v,lo,hi,avg){ if(!isNum(v)||!isNum(lo)||!isNum(hi)||hi<=lo) return "";
  const p=x=>Math.max(0,Math.min(100,(x-lo)/(hi-lo)*100));
  return `<div class="rangebar">${isNum(avg)?`<b style="left:${p(avg)}%" title="average"></b>`:""}<i style="left:calc(${p(v)}% - 1px)"></i></div>`; }
const tag = (html,tone="",attrs="") => `<span class="tag ${tone}" ${attrs}>${html}</span>`;

/* ---------------------------------------------------------------- icons, dropdowns, section tabs */
const ICON = {
  overview:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  monitor:'<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h1M4 12h1M4 18h1"/>',
  curves:'<path d="M3 20c3-9 7-13 18-15"/><circle cx="6" cy="13.5" r="1.4"/><circle cx="12" cy="8.2" r="1.4"/><circle cx="18" cy="5.6" r="1.4"/>',
  countries:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18"/>',
  credit:'<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h4"/>',
  banks:'<path d="M3 10 12 4l9 6"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18"/>',
  guide:'<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 7.5h.01"/>',
  up:'<path d="M12 19V5"/><path d="m6 11 6-6 6 6"/>',
  down:'<path d="M12 5v14"/><path d="m6 13 6 6 6-6"/>',
  award:'<circle cx="12" cy="9" r="6"/><path d="m8.5 14-1.5 8 5-3 5 3-1.5-8"/>',
  shield:'<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/>',
  coin:'<circle cx="12" cy="12" r="9"/><path d="M14.8 9.2c-.5-.8-1.5-1.2-2.8-1.2-1.7 0-2.8.8-2.8 1.9 0 2.7 5.6 1.4 5.6 4.2 0 1.1-1.1 1.9-2.8 1.9-1.4 0-2.4-.5-2.9-1.3M12 6.5v1.5M12 16v1.5"/>',
  alert:'<path d="M12 4 2.5 20h19z"/><path d="M12 10v4.5M12 17.5h.01"/>',
  trend:'<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  gauge:'<path d="M4.6 18a9 9 0 1 1 14.8 0"/><path d="m12 14 4-4"/>',
};
const icon = (k,s=16) => `<svg class="ico" width="${s}" height="${s}" style="width:${s}px;height:${s}px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[k]||""}</svg>`;

/* Dropdowns. Which ones are open survives the automatic refresh, which redraws the page. */
const OPEN = new Map();
document.addEventListener("toggle",e=>{ const d=e.target; if(d.tagName==="DETAILS"&&d.dataset.k) OPEN.set(d.dataset.k,d.open); },true);
function restoreOpen(root=document){ root.querySelectorAll("details[data-k]").forEach(d=>{ if(OPEN.has(d.dataset.k)) d.open=OPEN.get(d.dataset.k); }); }
const more = (k,body,label="How this works") => `<details class="more" data-k="${esc(k)}"><summary>${icon("info",14)}<span>${label}</span></summary><div class="more-body">${body}</div></details>`;
const fold = (k,title,body,open=false) => `<details class="fold" data-k="${esc(k)}"${open?" open":""}><summary>${title}</summary><div class="fold-body">${body}</div></details>`;
function secHead({eyebrow="",title,h="h2",lead="",right=""}){
  return `<div class="sec-head"><div class="grow">${eyebrow?`<div class="eyebrow">${eyebrow}</div>`:""}<${h}>${title}</${h}>${lead?`<p>${lead}</p>`:""}</div>${right}</div>`; }
function stat({label,ico="",value="",tone="",sub="",body="",open="",href=""}){
  const el=href?"a":"div", attrs=open?` data-open="${esc(open)}" role="button" tabindex="0"`:href?` href="${esc(href)}"`:"";
  return `<${el} class="stat${open||href?" click":""}"${attrs}><div class="stat-lab">${ico?icon(ico,14):""}<span>${label}</span></div>
    ${value!==""?`<div class="stat-val ${tone}">${value}</div>`:""}${body}${sub?`<div class="stat-sub">${sub}</div>`:""}</${el}>`;
}
const heroGrid = cards => { const c=cards.filter(Boolean); return `<div class="hero n${c.length}">${c.join("")}</div>`; };
const seg = (id,opts,cur,label="") => `${label?`<span class="seg-lab">${esc(label)}</span>`:""}<div class="seg" id="${id}" role="group"${label?` aria-label="${esc(label)}"`:""}>${opts.map(([k,l])=>`<button type="button" data-v="${esc(k)}" aria-pressed="${String(k)===String(cur)}">${esc(l)}</button>`).join("")}</div>`;
function bindSeg(id,fn){ document.querySelectorAll(`#${id} button`).forEach(b=>b.onclick=()=>fn(b.dataset.v)); }

const Views = {
  names:[], draw:{}, cur:null,
  init(names,draw={}){
    this.names=names; this.draw=draw; const h=location.hash.slice(1); this.cur=names.includes(h)?h:names[0];
    document.querySelectorAll("#views [data-view]").forEach(b=>{ b.insertAdjacentHTML("afterbegin",icon(b.dataset.view,17)); b.onclick=()=>this.go(b.dataset.view,true); });
    addEventListener("hashchange",()=>{ const h=location.hash.slice(1); if(this.names.includes(h)&&h!==this.cur) this.go(h,true); });
    document.addEventListener("click",e=>{ const a=e.target.closest('a[href^="#"]'); if(!a) return; const id=a.getAttribute("href").slice(1);
      if(this.names.includes(id)){ e.preventDefault(); Drawer.close(); this.go(id,true); return; }
      const el=id&&document.getElementById(id), v=el&&el.closest("[data-view]"); if(!v) return;
      e.preventDefault(); Drawer.close(); this.go(v.dataset.view,false); requestAnimationFrame(()=>el.scrollIntoView({behavior:"smooth",block:"start"})); });
    this.mark();
  },
  mark(){ document.querySelectorAll("#views [data-view]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.view===this.cur)); },
  apply(){ document.querySelectorAll("#app [data-view]").forEach(v=>v.hidden=v.dataset.view!==this.cur); this.mark(); this.draw[this.cur]?.(); },
  go(name,toTop){ this.cur=name; history.replaceState(null,"","#"+name); this.apply(); if(toTop) scrollTo({top:0}); },
};

/* ---------------------------------------------------------------- detail drawer */
const Drawer = {
  open(label,html,onClose){
    this.close(true);
    const scrim=document.createElement("div"); scrim.className="scrim"; scrim.id="scrim"; scrim.onclick=()=>this.close();
    const d=document.createElement("aside"); d.className="drawer"; d.id="drawer"; d.setAttribute("role","dialog"); d.setAttribute("aria-label",label);
    d.innerHTML=html; document.body.append(scrim,d); document.body.style.overflow="hidden";
    this.onClose=onClose;
    d.querySelector("#closeD")?.addEventListener("click",()=>this.close()); d.querySelector("#closeD")?.focus();
    d.querySelectorAll("a[href^='#']").forEach(a=>a.addEventListener("click",()=>this.close()));
    return d;
  },
  close(silent){ $("#scrim")?.remove(); $("#drawer")?.remove(); const t=$("#tip"); if(t) t.hidden=true; document.body.style.overflow="";
    if(!silent&&this.onClose) this.onClose(); },
};
function dTabs(tabs,cur){ return `<div class="dtabs" role="group" aria-label="Detail sections">${tabs.map(([k,l])=>`<button type="button" data-dtab="${k}" aria-pressed="${k===cur}">${esc(l)}</button>`).join("")}</div>`; }
function bindDTabs(d,cur,onShow){
  const bar=d.querySelector(".dtabs");
  const show=k=>{ d.querySelectorAll("[data-pane]").forEach(p=>p.hidden=p.dataset.pane!==k);
    d.querySelectorAll("[data-dtab]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.dtab===k)); onShow(k); };
  d.querySelectorAll("[data-dtab]").forEach(b=>b.onclick=()=>{ show(b.dataset.dtab); if(bar&&d.scrollTop>bar.offsetTop) d.scrollTop=bar.offsetTop; });
  show(cur);
}

/* ---------------------------------------------------------------- charts */
function sparkSVG(vals,{w=96,h=24,color,invert=true}={}){
  const v = (vals||[]).filter(x=>x!=null); if(v.length<2) return "";
  const mn=Math.min(...v), mx=Math.max(...v), r=mx-mn||1;
  const P = v.map((y,i)=>[i/(v.length-1)*(w-3)+1.5, h-2-(y-mn)/r*(h-4)]);
  const d = P.map((p,i)=>(i?"L":"M")+p[0].toFixed(1)+" "+p[1].toFixed(1)).join("");
  // for yields, a rising line is bad news for holders
  const up=v[v.length-1]>=v[0], c = color || ((invert?!up:up)?"var(--pos)":"var(--neg)");
  const last = P[P.length-1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${d}L${last[0]} ${h}L1.5 ${h}Z" fill="${c}" fill-opacity=".10"/>
    <path d="${d}" fill="none" stroke="${c}" stroke-width="1.4" vector-effect="non-scaling-stroke"/>
    <circle cx="${last[0]}" cy="${last[1]}" r="1.8" fill="${c}"/></svg>`;
}
function niceTicks(mn,mx,n=5){ const span=mx-mn||1, step0=span/n, mag=10**Math.floor(Math.log10(step0));
  const step=[1,2,2.5,5,10].map(s=>s*mag).find(s=>span/s<=n)||mag*10; const out=[];
  for(let v=Math.ceil(mn/step)*step; v<=mx+1e-9; v+=step) out.push(+v.toFixed(10)); return out; }
function showTip(e){ const tip=$("#tip"); tip.hidden=false;
  tip.style.left=Math.max(8,Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8))+"px"; tip.style.top=Math.max(8,e.clientY-tip.offsetHeight-12)+"px"; }
function hideTip(){ const t=$("#tip"); if(t) t.hidden=true; }
function bindTips(root){ root.querySelectorAll("[data-tip]").forEach(n=>{ n.addEventListener("mousemove",e=>{ $("#tip").innerHTML=n.dataset.tip; showTip(e); }); n.addEventListener("mouseleave",hideTip); }); }

/* Time-series line chart with a hover crosshair. t: shared timestamps; series: [{v:[], color, w, dash, name}] */
function lineChart(el,{t,series,h=240,fmt=v=>v.toFixed(2),baseline=null,baselineLabel="",area=0,zero=false}){
  if(!el) return;
  if(!t||t.length<2){ el.innerHTML='<p class="muted">Not enough history.</p>'; return; }
  const W = Math.max(280, el.clientWidth||600), H=h, L=8, R=62, T=10, B=24;
  const all = series.flatMap(s=>s.v).filter(v=>v!=null); if(baseline!=null) all.push(baseline); if(zero) all.push(0);
  let mn=Math.min(...all), mx=Math.max(...all); const pad=(mx-mn)*.06||1; mn-=pad; mx+=pad;
  const X = i => L + i/(t.length-1)*(W-L-R), Y = v => T + (1-(v-mn)/(mx-mn))*(H-T-B);
  const ticks = niceTicks(mn,mx,4);
  let g = ticks.map(v=>`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)" stroke-width="1"/>
    <text x="${W-R+6}" y="${Y(v)+4}" font-size="11" fill="var(--muted)" font-family="var(--mono)">${fmt(v)}</text>`).join("");
  const span = (t[t.length-1]-t[0])/86400, years = span>800, short = span<150;
  const seen=new Set(); let xl="";
  t.forEach((ts,i)=>{ const d=new Date(ts*1000); const key = years? d.getUTCFullYear() : short? d.getUTCFullYear()+"-"+d.getUTCMonth()+"-"+(d.getUTCDate()<15) : d.getUTCFullYear()+"-"+d.getUTCMonth();
    if(!seen.has(key)){ seen.add(key); if(i<2) return;
      if(years && span>2500 && d.getUTCFullYear()%2) return;
      if(!years && !short && d.getUTCMonth()%2) return;
      if(short && d.getUTCDate()>=15) return;
      const lab = years? d.getUTCFullYear() : d.toLocaleString(undefined,{month:"short",timeZone:"UTC"});
      xl+=`<text x="${X(i)}" y="${H-6}" font-size="11" fill="var(--muted)" text-anchor="middle">${lab}</text>`; }});
  if(baseline!=null) g+=`<line x1="${L}" x2="${W-R}" y1="${Y(baseline)}" y2="${Y(baseline)}" stroke="var(--faint)" stroke-dasharray="3 3"/>`+
    (baselineLabel?`<text x="${L+4}" y="${Y(baseline)-5}" font-size="11" fill="var(--muted)">${esc(baselineLabel)}</text>`:"");
  const lastIdx = v => { let i=v.length-1; while(i>0&&v[i]==null) i--; return i; };
  const paths = series.map((s,si)=>{ let d="",on=false;
    s.v.forEach((v,i)=>{ if(v==null){on=false;return;} d+=(on?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1); on=true; });
    const first=s.v.findIndex(v=>v!=null), last=lastIdx(s.v);
    const fill = (si===0&&area&&first>=0) ? `<path d="${d}L${X(last)} ${H-B}L${X(first)} ${H-B}Z" fill="${s.color}" fill-opacity=".08"/>` : "";
    return fill+`<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.w||2}" ${s.dash?`stroke-dasharray="${s.dash}"`:""} stroke-linejoin="round"/>`; }).join("");
  // the end label belongs to whichever series reaches furthest right (e.g. a forecast continuing an actual line)
  const lead = series.reduce((a,s)=>lastIdx(s.v)>lastIdx(a.v)?s:a, series[0]), s0=lead.v, li=lastIdx(s0);
  const end = s0[li]==null? "" : `<circle cx="${X(li)}" cy="${Y(s0[li])}" r="4" fill="${lead.color}" stroke="var(--surface)" stroke-width="2"/>
    <rect x="${W-R+2}" y="${Y(s0[li])-9}" width="${R-4}" height="18" rx="4" fill="${lead.color}"/>
    <text x="${W-R+6}" y="${Y(s0[li])+4}" font-size="11" fill="#fff" font-family="var(--mono)">${fmt(s0[li])}</text>`;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img">${g}${xl}${paths}${end}
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="var(--muted)" stroke-width="1" visibility="hidden"/>
    <rect x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="transparent"/></svg>`;
  const svg=el.querySelector("svg"), xh=svg.querySelector(".xh"), n=t.length-1;
  svg.addEventListener("mousemove",e=>{ const r=svg.getBoundingClientRect(); const x=(e.clientX-r.left)*(W/r.width);
    const i=Math.max(0,Math.min(n,Math.round((x-L)/(W-L-R)*n))); xh.setAttribute("x1",X(i)); xh.setAttribute("x2",X(i)); xh.setAttribute("visibility","visible");
    $("#tip").innerHTML = `<b>${esc(dateStr(t[i]))}</b>`+series.map(s=>s.v[i]==null?"":`<br><span style="color:${s.color}">●</span> ${esc(s.name)} ${esc(fmt(s.v[i]))}`).join("");
    showTip(e); });
  svg.addEventListener("mouseleave",()=>{xh.setAttribute("visibility","hidden");hideTip();});
}

/* Yield curve: x = years to maturity on a square-root scale (so the short end is readable), y = yield.
   sets: [{pts:[[years,yield]...], color, name, dash, w, dots}] */
const CURVE_TICKS = [[0.25,"3M"],[1,"1Y"],[2,"2Y"],[5,"5Y"],[10,"10Y"],[20,"20Y"],[30,"30Y"],[50,"50Y"]];
function curveChart(el,{sets,h=280,fmt=v=>v.toFixed(2)+"%"}){
  if(!el) return; sets=sets.filter(s=>s.pts&&s.pts.length);
  if(!sets.length){ el.innerHTML='<p class="muted">No curve data.</p>'; return; }
  const W=Math.max(280,el.clientWidth||600), H=h, L=46, R=16, T=12, B=26;
  const xs=sets.flatMap(s=>s.pts.map(p=>p[0])), ys=sets.flatMap(s=>s.pts.map(p=>p[1]));
  const x0=Math.sqrt(Math.max(0,Math.min(...xs)*0.9)), x1=Math.sqrt(Math.max(...xs)*1.04);
  let mn=Math.min(...ys), mx=Math.max(...ys); const pad=(mx-mn)*.1||0.25; mn-=pad; mx+=pad;
  const X=x=>L+(Math.sqrt(x)-x0)/(x1-x0||1)*(W-L-R), Y=v=>T+(1-(v-mn)/(mx-mn))*(H-T-B);
  let g=niceTicks(mn,mx,5).map(v=>`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${L-6}" y="${Y(v)+4}" font-size="11" text-anchor="end" fill="var(--muted)" font-family="var(--mono)">${fmt(v)}</text>`).join("");
  g+=CURVE_TICKS.filter(([x])=>Math.sqrt(x)>=x0-0.01&&Math.sqrt(x)<=x1+0.01).map(([x,l])=>`<line x1="${X(x)}" x2="${X(x)}" y1="${T}" y2="${H-B}" stroke="var(--line)" stroke-dasharray="2 4"/><text x="${X(x)}" y="${H-7}" font-size="11" text-anchor="middle" fill="var(--muted)">${l}</text>`).join("");
  const lines=sets.map(s=>{ const p=s.pts.slice().sort((a,b)=>a[0]-b[0]);
    const d=p.map((q,i)=>(i?"L":"M")+X(q[0]).toFixed(1)+" "+Y(q[1]).toFixed(1)).join("");
    return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.w||2}" ${s.dash?`stroke-dasharray="${s.dash}"`:""} stroke-linejoin="round"/>`+
      (s.dots?p.map(q=>`<circle cx="${X(q[0])}" cy="${Y(q[1])}" r="4" fill="${s.color}" stroke="var(--surface)" stroke-width="2"/>`).join(""):""); }).join("");
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Yield curve">${g}${lines}
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="var(--muted)" visibility="hidden"/><rect x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="transparent"/></svg>`;
  const svg=el.querySelector("svg"), xh=svg.querySelector(".xh");
  const interp=(pts,x)=>{ const p=pts.slice().sort((a,b)=>a[0]-b[0]); if(x<p[0][0]-0.3||x>p[p.length-1][0]+0.3) return null;
    if(x<=p[0][0]) return p[0][1]; for(let i=1;i<p.length;i++) if(x<=p[i][0]) return p[i-1][1]+(p[i][1]-p[i-1][1])*(x-p[i-1][0])/(p[i][0]-p[i-1][0]); return p[p.length-1][1]; };
  svg.addEventListener("mousemove",e=>{ const r=svg.getBoundingClientRect(), px=(e.clientX-r.left)*(W/r.width);
    const sx=x0+(px-L)/(W-L-R)*(x1-x0), x=Math.max(0.02,sx*sx); xh.setAttribute("x1",X(x)); xh.setAttribute("x2",X(x)); xh.setAttribute("visibility","visible");
    const lab=x<1?`${Math.round(x*12)} months`:`${x.toFixed(x<10?1:0)} years`;
    $("#tip").innerHTML=`<b>${lab}</b>`+sets.map(s=>{ const v=interp(s.pts,x); return v==null?"":`<br><span style="color:${s.color}">●</span> ${esc(s.name)} ${esc(fmt(v))}`; }).join("");
    showTip(e); });
  svg.addEventListener("mouseleave",()=>{xh.setAttribute("visibility","hidden");hideTip();});
}

/* Scatter with a best-fit line. pts: [{x,y,label,key,tip,color}]. Labels are nudged apart so neighbours stay readable. */
function scatterChart(el,{pts,xlab,ylab,xfmt=v=>v.toFixed(1),yfmt=v=>v.toFixed(1),fit=true,h,zeroX=false,zeroY=false,quad=null}){
  if(!el) return; pts=pts.filter(p=>isNum(p.x)&&isNum(p.y));
  if(pts.length<3){ el.innerHTML='<p class="muted">Not enough markets have both numbers.</p>'; return; }
  const W=Math.max(300,el.clientWidth||560), H=h||Math.round(Math.min(W*0.7,480)), L=50, R=18, T=14, B=40;
  let xs=pts.map(p=>p.x), ys=pts.map(p=>p.y); if(zeroX) xs.push(0); if(zeroY) ys.push(0);
  let xmn=Math.min(...xs), xmx=Math.max(...xs), ymn=Math.min(...ys), ymx=Math.max(...ys);
  const px=(xmx-xmn)*.06||1, py=(ymx-ymn)*.08||1; xmn-=px; xmx+=px; ymn-=py; ymx+=py;
  const X=v=>L+(v-xmn)/(xmx-xmn)*(W-L-R), Y=v=>T+(1-(v-ymn)/(ymx-ymn))*(H-T-B);
  let g=niceTicks(ymn,ymx,5).map(v=>`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${L-6}" y="${Y(v)+4}" font-size="11" text-anchor="end" fill="var(--muted)" font-family="var(--mono)">${yfmt(v)}</text>`).join("");
  g+=niceTicks(xmn,xmx,6).map(v=>`<text x="${X(v)}" y="${H-B+16}" font-size="11" text-anchor="middle" fill="var(--muted)" font-family="var(--mono)">${xfmt(v)}</text>`).join("");
  g+=`<text x="${(L+W-R)/2}" y="${H-6}" font-size="12" text-anchor="middle" fill="var(--muted)">${esc(xlab)}</text>
      <text x="12" y="${(T+H-B)/2}" font-size="12" text-anchor="middle" fill="var(--muted)" transform="rotate(-90 12 ${(T+H-B)/2})">${esc(ylab)}</text>`;
  if(quad) g+=quad(X,Y,{L,R,T,B,W,H});
  let fitInfo=null;
  if(fit){ const n=pts.length, mx=pts.reduce((a,p)=>a+p.x,0)/n, my=pts.reduce((a,p)=>a+p.y,0)/n;
    const sxx=pts.reduce((a,p)=>a+(p.x-mx)**2,0), sxy=pts.reduce((a,p)=>a+(p.x-mx)*(p.y-my),0), syy=pts.reduce((a,p)=>a+(p.y-my)**2,0);
    if(sxx>0){ const b=sxy/sxx, a=my-b*mx, r2=syy>0?(sxy*sxy)/(sxx*syy):0; fitInfo={a,b,r2};
      g+=`<line x1="${X(xmn)}" x2="${X(xmx)}" y1="${Y(a+b*xmn)}" y2="${Y(a+b*xmx)}" stroke="var(--faint)" stroke-width="1.5" stroke-dasharray="6 4"/>`; } }
  const placed=[]; let dots="";
  pts.slice().sort((a,b)=>a.y-b.y).forEach(p=>{ const x=X(p.x), y=Y(p.y);
    let ly=y+4; while(placed.some(q=>Math.abs(q.y-ly)<11&&Math.abs(q.x-x)<26)) ly+=11; placed.push({x,y:ly});
    dots+=`<g class="dotg" ${p.key?`data-open="${esc(p.key)}"`:""} data-tip="${esc(p.tip||p.label)}"><circle cx="${x}" cy="${y}" r="5" fill="${p.color||"var(--s1)"}" stroke="var(--surface)" stroke-width="2"/>
      <text x="${x+8}" y="${ly}" font-size="11" fill="var(--ink)">${esc(p.label)}</text></g>`; });
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(ylab)} against ${esc(xlab)}">${g}${dots}</svg>`;
  bindTips(el);
  return fitInfo;
}

/* Horizontal bars from zero (can be negative). items: [{label, v, sub, key, color}] */
function barsSVG(items,{fmt=v=>v.toFixed(1),labelW=150,rowH=26}={}){
  const W=600, L=labelW, H=items.length*rowH+8;
  const vals=items.map(x=>x.v??0), lo=Math.min(0,...vals), hi=Math.max(0,...vals), span=(hi-lo)||1;
  const padL=lo<0?58:6, padR=hi>0?70:6;  // room for the value labels beside the bars
  const sx=v=>L+padL+(v-lo)/span*(W-L-padL-padR), zero=sx(0);
  const rows=items.map((x,i)=>{ const y=4+i*rowH, v=x.v, x0=Math.min(zero,sx(v??0)), w=Math.abs(sx(v??0)-zero);
    const ty=y+rowH/2+4;
    return `<g ${x.key?`data-open="${esc(x.key)}" style="cursor:pointer"`:""}><text x="0" y="${ty}" font-size="12.5" fill="var(--ink)">${esc(x.label)}</text>
      ${x.sub?`<text x="${L-8}" y="${ty}" font-size="11" fill="var(--faint)" text-anchor="end">${esc(x.sub)}</text>`:""}
      ${v==null?"":`<rect x="${x0}" y="${y+(rowH-14)/2}" width="${Math.max(1,w)}" height="14" rx="3" fill="${x.color||(v>=0?"var(--s1)":"var(--dneg)")}"/>
      <text x="${v>=0?x0+w+6:x0-6}" y="${ty}" font-size="12" font-family="var(--mono)" fill="var(--ink)" text-anchor="${v>=0?"start":"end"}">${esc(fmt(v))}</text>`}</g>`; }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img"><line x1="${zero}" x2="${zero}" y1="0" y2="${H}" stroke="var(--line)"/>${rows}</svg>`;
}

/* ---------------------------------------------------------------- live data loop */
function newerSite(v){
  if(!STATIC||!v||SITE_VERSION==="dev"||v===SITE_VERSION) return false;
  try{ const last=JSON.parse(sessionStorage.getItem("siteReload")||"{}");
    if(last.v===v&&Date.now()-last.at<15*60*1000) return false;
    sessionStorage.setItem("siteReload",JSON.stringify({v,at:Date.now()})); }catch(e){ return false; }
  return true;
}
const apiUrl = (path,force) => STATIC ? `api/${path}.json?t=${Date.now()}` : `/api/${path}${force?"?force=1":""}`;
function startLoop({url,onData}){
  const L={lastOk:0,nextAt:0,data:null};
  async function load(force){
    const btn=$("#refresh"); btn.disabled=true; btn.textContent="Refreshing…";
    try{
      const res=await fetch(apiUrl(url,force),{cache:"no-store"});
      if(!res.ok) throw new Error("Server replied "+res.status);
      const data=await res.json(); if(data.error) throw new Error(data.error);
      if(newerSite(data.site)){ location.reload(); return; }
      L.data=data; L.lastOk=Date.now(); onData(data);
      $("#dot").className="dot";
    }catch(e){
      $("#dot").className="dot err";
      if(!L.data) $("#app").innerHTML=`<div class="loading err">Couldn't load bond prices: ${esc(e.message)}.<br>${STATIC?"Check your connection, then press Reload.":"Make sure <code>py app/server.py</code> is running, then press Refresh."}</div>`;
    }finally{ btn.disabled=false; btn.textContent=STATIC?"Reload":"Refresh now"; L.nextAt=Date.now()+REFRESH_MS; stamp(); }
  }
  function stamp(){
    if(!L.data) return;
    const mt=new Date(L.data.marketTime*1000), gen=new Date(L.data.generated*1000);
    const left=Math.max(0,L.nextAt-Date.now()), mm=Math.floor(left/60000), ss=Math.floor(left/1000)%60;
    if(Date.now()-L.lastOk>REFRESH_MS*3) $("#dot").className="dot stale";
    const last=mt.toLocaleString([], {weekday:"short",hour:"2-digit",minute:"2-digit"});
    if(STATIC){
      const old=Date.now()-gen>60*60*1000; if(old) $("#dot").className="dot stale";
      $("#stamp").textContent=`${old?"Delayed":"Live"} · yields updated ${ago(gen.getTime())} (every ~15 min) · latest trade ${last}`;
      return;
    }
    $("#stamp").textContent=`Live · checked ${gen.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})} · latest trade ${last} · next check in ${mm?mm+" min":ss+" s"}`;
  }
  $("#refresh").onclick=()=>load(true);
  document.addEventListener("click",e=>{ const t=e.target.closest("[data-open]"); if(t&&typeof openDetail==="function") openDetail(t.dataset.open); });
  setInterval(()=>{ stamp(); if(L.nextAt && Date.now()>=L.nextAt) load(false); },1000);
  document.addEventListener("keydown",e=>{ if(e.key==="Escape") Drawer.close();
    if((e.key==="Enter"||e.key===" ")&&e.target.matches?.("[data-open][role=button]")){e.preventDefault();e.target.click();} });
  load(false);
  return L;
}
