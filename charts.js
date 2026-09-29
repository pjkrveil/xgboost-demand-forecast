/* Shared, dependency-free daily/monthly forecast chart for both engines. */
window.ForecastChart = function(host, records, options={}) {
  const doc=host.ownerDocument, ns='http://www.w3.org/2000/svg';
  const series=[
    {key:'business_plan',label:'계획량',color:'#0d9488',width:2.2,dash:'12 4'},
    {key:'prediction_baseline',label:'기본 기온 예측',color:'#a855f7',width:1.5},
    {key:'prediction_minus',label:'−delta',color:'#2563eb',width:1.8,dash:'4 4'},
    {key:'prediction_plus',label:'+delta',color:'#93c5fd',width:1.8,dash:'7 5'},
    {key:'prediction',label:'MC 예측',color:'#0284c7',width:2.8},
    {key:'actual',label:'실측 GT',color:'#ea580c',width:2},
    {key:'temp_max',label:'입력 최고기온',color:'#fca5a5',width:1.6,dash:'8 3 2 3',temperature:true},
    {key:'temp_min',label:'입력 최저기온',color:'#a3d977',width:1.6,dash:'8 3 2 3',temperature:true},
    {key:'temp_avg',label:'입력 평균기온',color:'#b08b00',width:2,temperature:true},
    {key:'observed_temp_max',label:'실측 최고기온',color:'#be123c',width:1.8,dash:'3 3',temperature:true},
    {key:'observed_temp_min',label:'실측 최저기온',color:'#15803d',width:1.8,dash:'3 3',temperature:true},
    {key:'observed_temp_avg',label:'실측 평균기온',color:'#475569',width:2,dash:'10 4',temperature:true}
  ];
  const finite=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
  const fmt=v=>finite(v)?Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2}):'—';
  const node=(tag,attrs={},text)=>{const n=doc.createElement(tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!=null)n.textContent=text;return n;};
  const svgNode=(tag,attrs={},text)=>{const n=doc.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!=null)n.textContent=text;return n;};
  const root=node('div',{class:'forecast-viz'}),toolbar=node('div',{class:'viz-toolbar'}),legend=node('div',{class:'viz-legend'}),stage=node('div',{class:'viz-stage'}),tooltip=node('div',{class:'viz-readout','aria-label':'선택 지점 예측 정보'});
  let mode=options.mode||'daily',index=0,zoom=null;const hidden=new Set();
  let data=[];const modeButtons=[];
  for(const [value,label]of [['daily','일자별'],['monthly','월별 합계']]){const b=node('button',{type:'button'},label);b.onclick=()=>{mode=value;zoom=null;draw();};toolbar.append(b);modeButtons.push([b,value]);}
  toolbar.append(node('span',{class:'viz-subtitle'},options.subtitle||'포인트에 마우스를 올리거나 그래프에서 ← → 키를 누르세요.'));
  const resetZoom=node('button',{type:'button'},'확대 초기화');resetZoom.onclick=()=>{zoom=null;draw();};toolbar.append(resetZoom,node('span',{class:'viz-subtitle'},'드래그 확대 · 기본 기온 예측 = 기온 변동 전 예측 · MC 예측 = 시나리오 대표값(미적용 시 기본 예측)'));
  const available=series.filter(s=>records.some(r=>finite(r[s.key])));
  const legendGroups=[
    ['사입량',['business_plan','actual','prediction_baseline','prediction','prediction_minus','prediction_plus']],
    ['예측에 사용된 기온',['temp_avg','temp_max','temp_min']],
    ['실측 기온',['observed_temp_avg','observed_temp_max','observed_temp_min']]
  ];
  for(const [title,keys] of legendGroups){
    const group=node('div',{class:'viz-legend-group','aria-label':title}),items=node('div',{class:'viz-legend-items'});
    group.append(node('strong',{class:'viz-legend-heading'},title),items);
    for(const key of keys){
      const s=series.find(s=>s.key===key),present=available.includes(s);
      const label=s.temperature?s.label.replace(/^(입력|실측) /,''):s.label;
      const b=node('button',{type:'button','aria-pressed':String(present)}),swatch=node('span',{class:'viz-swatch'});
      swatch.style.borderTop=`3px ${s.dash?'dashed':'solid'} ${s.color}`;b.append(swatch,doc.createTextNode(label));
      if(!present){b.disabled=true;b.title='해당 데이터 없음';}
      else b.onclick=()=>{hidden.has(s.key)?hidden.delete(s.key):hidden.add(s.key);b.setAttribute('aria-pressed',String(!hidden.has(s.key)));draw();};
      items.append(b);
    }
    legend.append(group);
  }
  const details=node('details'),summary=node('summary',{},'일자·월별 값과 오차 확인'),scroll=node('div',{class:'viz-table'});
  const errorPanel=node('section',{class:'viz-error-panel'});
  details.append(summary,scroll);root.append(toolbar,legend,stage,errorPanel,tooltip,details);host.replaceChildren(root);
  function aggregate(){
    if(mode==='daily')return records.map(r=>({...r,date:String(r.date).slice(0,10),days:1,gt:finite(r.actual)?1:0}));
    const months=new Map();
    for(const r of records){const month=String(r.date).slice(0,7);if(!months.has(month))months.set(month,{date:month,days:0,gt:0,counts:{}});const b=months.get(month);b.days++;if(finite(r.actual))b.gt++;for(const s of series)if(finite(r[s.key])){b[s.key]=(b[s.key]||0)+Number(r[s.key]);b.counts[s.key]=(b.counts[s.key]||0)+1;}}
    for(const b of months.values())for(const s of series)if(b.counts[s.key]!==b.days)b[s.key]=null;else if(s.temperature)b[s.key]/=b.days;
    return [...months.values()];
  }
  function errors(r,key){if(!finite(r.actual)||!finite(r[key]))return {difference:null,error:null};const difference=Number(r[key])-Number(r.actual);return {difference,error:Number(r.actual)===0?null:Math.abs(difference)/Math.abs(Number(r.actual))*100};}
  function draw(){
    data=aggregate();if(zoom)data=data.filter(r=>r.date>=zoom[0]&&r.date<=zoom[1]);resetZoom.disabled=!zoom;modeButtons.forEach(([b,v])=>{b.classList.toggle('active',mode===v);b.setAttribute('aria-pressed',String(mode===v));});
    const visible=available.filter(s=>!hidden.has(s.key));
    const values=data.flatMap(r=>visible.filter(s=>!s.temperature&&finite(r[s.key])).map(s=>Number(r[s.key])));
    const lo=values.length?Math.min(...values):0,hi=values.length?Math.max(...values):1,pad=Math.max(1,(hi-lo)*.08);
    const low=zoom?lo-pad:Math.min(0,lo),high=zoom?hi+pad:Math.max(1,hi)*1.08,W=1100,H=410,L=95,R=85,T=25,B=60;
    const temps=data.flatMap(r=>visible.filter(s=>s.temperature&&finite(r[s.key])).map(s=>Number(r[s.key])));
    const tlo=temps.length?Math.min(...temps)-1:0,thi=temps.length?Math.max(...temps)+1:1;
    const ty=v=>H-B-(Number(v)-tlo)/(thi-tlo)*(H-T-B),sy=(s,v)=>s.temperature?ty(v):y(v);
    const x=i=>L+i*(W-L-R)/Math.max(data.length-1,1),y=v=>H-B-(Number(v)-low)/(high-low)*(H-T-B);
    const svg=svgNode('svg',{viewBox:`0 0 ${W} ${H}`,tabindex:'0',role:'img','aria-label':`${mode==='daily'?'일별':'월별'} 수요 예측 및 GT 비교`});
    for(let i=0;i<=4;i++){const value=low+(high-low)*i/4;svg.append(svgNode('line',{x1:L,y1:y(value),x2:W-R,y2:y(value),class:'viz-grid'}),svgNode('text',{x:L-12,y:y(value)+4,'text-anchor':'end'},fmt(value)));}
    if(temps.length){svg.append(svgNode('text',{x:W-R+8,y:15},'기온 °C'));for(let i=0;i<=4;i++){const v=tlo+(thi-tlo)*i/4;svg.append(svgNode('text',{x:W-R+8,y:ty(v)+4},fmt(v)));}}
    const ticks=Math.min(6,data.length);for(let i=0;i<ticks;i++){const j=Math.round(i*(data.length-1)/Math.max(ticks-1,1));svg.append(svgNode('text',{x:x(j),y:H-24,'text-anchor':i===0?'start':i===ticks-1?'end':'middle'},data[j].date));}
    for(const s of visible){let d='',previous=false;data.forEach((r,i)=>{if(!finite(r[s.key])){previous=false;return;}d+=`${previous?'L':'M'}${x(i)},${sy(s,r[s.key])} `;previous=true;});svg.append(svgNode('path',{d,fill:'none',stroke:s.color,'stroke-width':s.width,'stroke-dasharray':s.dash||'none','stroke-linejoin':'round','stroke-linecap':'round'}));
      // Hollow GT markers make overlap visible even on the same curve.
      if(s.key==='actual'||data.length===1)data.forEach((r,i)=>{if(finite(r[s.key]))svg.append(svgNode('circle',{cx:x(i),cy:sy(s,r[s.key]),r:mode==='monthly'?2:1.1,fill:'var(--surface-solid,white)',stroke:s.color,'stroke-width':.8}));});
    }
    const focus=svgNode('g',{visibility:'hidden'}),hair=svgNode('line',{y1:T,y2:H-B,class:'viz-crosshair'}),dots=svgNode('g');focus.append(hair,dots);svg.append(focus);
    stage.replaceChildren(svg);
    let errorHair=null,errorDate=null;
    const dateLabel=svgNode('text',{y:H-5,'text-anchor':'middle',class:'viz-cursor-date',visibility:'hidden'});svg.append(dateLabel);
    function clearCursor(){focus.setAttribute('visibility','hidden');dateLabel.setAttribute('visibility','hidden');if(errorHair)errorHair.setAttribute('visibility','hidden');if(errorDate)errorDate.setAttribute('visibility','hidden');}
    function dateText(row){if(mode==='daily')return row.date;const dates=records.map(r=>String(r.date).slice(0,10)).filter(d=>d.slice(0,7)===row.date).sort();return dates.length?dates[0]+' ~ '+dates[dates.length-1]:row.date+'-01';}
    function setDate(label,row){if(!label)return;label.textContent=dateText(row);label.setAttribute('x',Math.max(L+105,Math.min(W-R-105,x(index))));label.setAttribute('visibility','visible');}
    function renderReadout(row){
      row=row||{};
      const table=node('table',{class:'viz-readout-table viz-demand-readout'}),head=node('tr');
      for(const label of ['날짜','구분','값','실측 GT','GT 대비 차이','GT 대비 오차율','−δ 예측','+δ 예측'])head.append(node('th',{scope:'col'},label));
      const thead=node('thead'),tbody=node('tbody');thead.append(head);
      for(const [key,label] of [['prediction','예측값'],['business_plan','계획량']]){
        const tr=node('tr',{'data-series':key}),e=errors(row,key);
        if(key==='prediction')tr.append(node('td',{rowspan:'2',class:'viz-readout-date'},row.date?dateText(row):'날짜 선택'));
        tr.append(node('th',{scope:'row'},label));
        for(const value of [fmt(row[key]),fmt(row.actual),fmt(e.difference),finite(e.error)?fmt(e.error)+'%':'—',key==='prediction'?fmt(row.prediction_minus):'—',key==='prediction'?fmt(row.prediction_plus):'—'])tr.append(node('td',{},value));
        tbody.append(tr);
      }
      table.append(thead,tbody);
      const weather=node('table',{class:'viz-readout-table viz-weather-readout'}),whead=node('thead'),wrow=node('tr'),wbody=node('tbody');
      weather.append(node('caption',{},mode==='monthly'?'기온 °C · 일별 기온의 월평균 (결측 항목은 —)':'기온 °C'));
      for(const label of ['구분','최고기온','평균기온','최저기온'])wrow.append(node('th',{scope:'col'},label));whead.append(wrow);
      for(const [prefix,label] of [['','예측 입력 기온'],['observed_','실측 기온']]){
        const tr=node('tr');tr.append(node('th',{scope:'row'},label));
        for(const col of ['temp_max','temp_avg','temp_min'])tr.append(node('td',{},fmt(row[prefix+col])));wbody.append(tr);
      }
      weather.append(whead,wbody);tooltip.replaceChildren(table,weather);
    }
    function reset(){renderReadout(null);clearCursor();}
    reset();
    function select(i){
      if(!data.length)return;
      index=Math.max(0,Math.min(data.length-1,i));const row=data[index];
      focus.setAttribute('visibility','visible');hair.setAttribute('x1',x(index));hair.setAttribute('x2',x(index));dots.replaceChildren();
      if(errorHair){errorHair.setAttribute('x1',x(index));errorHair.setAttribute('x2',x(index));errorHair.setAttribute('visibility','visible');}
      setDate(dateLabel,row);setDate(errorDate,row);
      renderReadout(row);
      for(const s of visible)if(finite(row[s.key]))dots.append(svgNode('circle',{cx:x(index),cy:sy(s,row[s.key]),r:2.5,fill:s.color,stroke:'var(--surface-solid,white)','stroke-width':1.5}));
    }
    const local=(element,e)=>{const m=element.getScreenCTM();if(!m)return null;const p=element.createSVGPoint();p.x=e.clientX;p.y=e.clientY;return p.matrixTransform(m.inverse());};
    const at=v=>Math.max(0,Math.min(data.length-1,Math.round((v-L)/(W-L-R)*Math.max(data.length-1,1))));
    let drag=null;
    const shade=svgNode('rect',{y:T,height:H-T-B,fill:'#0284c7',opacity:'.15',visibility:'hidden'});svg.append(shade);
    svg.onpointerdown=e=>{const p=local(svg,e);if(e.button!==0||!p||data.length<2||p.x<L||p.x>W-R||p.y<T||p.y>H-B)return;drag=p.x;svg.setPointerCapture(e.pointerId);e.preventDefault();};
    svg.onpointermove=e=>{const p=local(svg,e);if(!p)return;if(drag!==null){const end=Math.max(L,Math.min(W-R,p.x));shade.setAttribute('x',Math.min(drag,end));shade.setAttribute('width',Math.abs(drag-end));shade.setAttribute('visibility','visible');return;}if(p.x>=L&&p.x<=W-R&&p.y>=T&&p.y<=H-B)select(at(p.x));else clearCursor();};
    svg.onpointerup=e=>{if(drag===null)return;const start=drag,p=local(svg,e);drag=null;shade.setAttribute('visibility','hidden');if(svg.hasPointerCapture(e.pointerId))svg.releasePointerCapture(e.pointerId);if(!p||Math.abs(start-p.x)<8)return;const a=at(Math.min(start,p.x)),b=at(Math.max(start,p.x));if(b>a){zoom=[data[a].date,data[b].date];index=0;draw();}};
    svg.onpointercancel=svg.onlostpointercapture=()=>{drag=null;shade.setAttribute('visibility','hidden');};
    svg.onpointerleave=clearCursor;
    svg.onblur=clearCursor;
    svg.onfocus=()=>select(index);svg.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();select(index+(e.key==='ArrowRight'?1:-1));}if(e.key==='Escape'){if(zoom){zoom=null;draw();}else reset();}};
    const errorSeries=[
      {key:'prediction',label:'예측',positive:'#2563eb',negative:'#dc2626'},
      {key:'business_plan',label:'계획',positive:'#16a34a',negative:'#eab308'}
    ];
    const residuals=data.map(r=>errorSeries.map(s=>({...s,value:errors(r,s.key).difference})).filter(s=>finite(s.value)));
    const paired=residuals.flat();
    errorPanel.replaceChildren();
    errorPanel.append(node('div',{class:'viz-error-caption'},'차이 = 예측값 또는 계획량 − 실측 GT · 절대 차이가 큰 막대는 뒤에, 작은 막대는 앞에 표시'));
    const errorLegend=node('div',{class:'viz-error-legend','aria-label':'차이 막대 색상'});
    for(const s of errorSeries)for(const [sign,color,label] of [['negative',s.negative,'과소 (−)'],['positive',s.positive,'과대 (+)']]){
      const item=node('span'),swatch=node('i',{'aria-hidden':'true'});swatch.style.backgroundColor=color;item.append(swatch,doc.createTextNode(s.label+' '+label));errorLegend.append(item);
    }
    errorPanel.append(errorLegend);
    if(!paired.length){errorPanel.append(node('p',{},mode==='monthly'?'표시 구간에 GT와 함께 비교할 완전한 월별 예측·계획 값이 없습니다. 일별로 전환하거나 입력 자료를 확인하세요.':'표시 구간에 실측 GT와 예측값 또는 계획량이 함께 있는 날짜가 없습니다. GT 비교와 입력 자료를 확인하세요.'));}
    else{
      const EH=180,ET=20,EB=35,bound=Math.max(1,...paired.map(s=>Math.abs(s.value)))*1.1;
      const ey=v=>ET+(bound-v)/(2*bound)*(EH-ET-EB),zero=ey(0);
      const esvg=svgNode('svg',{viewBox:`0 0 ${W} ${EH}`,class:'viz-error-svg',tabindex:'0',role:'img','aria-label':'예측값 및 계획량의 실측 GT 대비 차이 막대 그래프'});
      for(const value of [-bound,0,bound]){esvg.append(svgNode('line',{x1:L,x2:W-R,y1:ey(value),y2:ey(value),stroke:value===0?'#64748b':'#cbd5e1','stroke-width':value===0?1.4:.6}),svgNode('text',{x:L-10,y:ey(value)+4,'text-anchor':'end'},fmt(value)));}
      const bw=Math.max(.5,Math.min(24,(W-L-R)/Math.max(data.length,1)*.7));
      residuals.forEach((bars,i)=>{
        // SVG paints later elements on top. Sort absolute magnitudes for both signs.
        const ordered=[...bars].sort((a,b)=>Math.abs(b.value)-Math.abs(a.value));
        const group=svgNode('g',{'data-date':data[i].date,class:'viz-error-bars'});
        ordered.forEach((s,j)=>{
          // Identical same-sign errors retain both colors via a narrower front bar.
          const tie=j>0&&ordered[j-1].value===s.value;
          const width=bw*(tie?.55:1),left=Math.max(L,x(i)-width/2),right=Math.min(W-R,x(i)+width/2);
          const rect=svgNode('rect',{x:left,y:Math.min(zero,ey(s.value)),width:right-left,height:Math.abs(ey(s.value)-zero),fill:s.value>=0?s.positive:s.negative,'fill-opacity':1,'data-series':s.key,'data-difference':s.value,class:'viz-error-bar'});
          rect.append(svgNode('title',{},`${data[i].date} · ${s.label} − GT: ${fmt(s.value)}`));group.append(rect);
        });
        esvg.append(group);
      });
      for(let i=0;i<ticks;i++){const j=Math.round(i*(data.length-1)/Math.max(ticks-1,1));esvg.append(svgNode('text',{x:x(j),y:EH-25,'text-anchor':i===0?'start':i===ticks-1?'end':'middle'},data[j].date));}
      errorHair=svgNode('line',{y1:ET,y2:EH-EB,class:'viz-crosshair',visibility:'hidden','pointer-events':'none'});
      errorDate=svgNode('text',{y:EH-2,'text-anchor':'middle',class:'viz-cursor-date',visibility:'hidden'});esvg.append(errorHair,errorDate);
      esvg.onpointermove=e=>{const p=local(esvg,e);if(p&&p.x>=L&&p.x<=W-R&&p.y>=ET&&p.y<=EH-EB)select(at(p.x));else clearCursor();};esvg.onpointerleave=clearCursor;
      esvg.onblur=clearCursor;
      esvg.onfocus=()=>select(index);esvg.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();select(index+(e.key==='ArrowRight'?1:-1));}};
      errorPanel.append(esvg,node('div',{class:'viz-error-caption'},`예측 비교 ${paired.filter(s=>s.key==='prediction').length}/${data.length}개 · 계획 비교 ${paired.filter(s=>s.key==='business_plan').length}/${data.length}개${paired.every(s=>s.value===0)?' · 모든 차이가 0입니다.':''}`));
    }
    const table=node('table'),thead=node('thead'),tr=node('tr');for(const label of ['날짜','예측값','계획량','실측 GT','예측−GT','예측 오차율','계획−GT','계획 오차율','−delta','+delta','GT 일수'])tr.append(node('th',{},label));thead.append(tr);table.append(thead);const body=node('tbody');
    for(const r of data){const e=errors(r,'prediction'),plan=errors(r,'business_plan'),tr=node('tr');for(const v of [r.date,fmt(r.prediction),fmt(r.business_plan),fmt(r.actual),fmt(e.difference),finite(e.error)?fmt(e.error)+'%':'—',fmt(plan.difference),finite(plan.error)?fmt(plan.error)+'%':'—',fmt(r.prediction_minus),fmt(r.prediction_plus),`${r.gt}/${r.days}`])tr.append(node('td',{},v));body.append(tr);}table.append(body);scroll.replaceChildren(table);
    if(data.length){select(index);clearCursor();}
  }
  draw();
};
