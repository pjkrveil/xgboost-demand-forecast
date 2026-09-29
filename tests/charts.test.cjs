/* Synthetic chart regressions: signs, draw order, readouts and missing data. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const source=fs.readFileSync(process.argv[2]||path.join(__dirname,'../charts.js'),'utf8');
function chart(records){const dom=new JSDOM('<div id="chart"></div>',{runScripts:'outside-only'});dom.window.eval(source);const host=dom.window.document.getElementById('chart');dom.window.ForecastChart(host,records);return {dom,host};}
const values=[
 {prediction:130,business_plan:110,actual:100},
 {prediction:95,business_plan:75,actual:100},
 {prediction:80,business_plan:140,actual:100},
 {prediction:110,business_plan:110,actual:100},
 {prediction:5,business_plan:0,actual:0},
 {prediction:110,business_plan:120,actual:null},
 {prediction:null,business_plan:80,actual:100},
 {prediction:0,business_plan:null,actual:10},
].map((r,i)=>({...r,date:`2026-01-${String(i+1).padStart(2,'0')}`,temp_max:10,temp_avg:0,temp_min:-5,observed_temp_max:9,observed_temp_avg:-1,observed_temp_min:-7,prediction_minus:90,prediction_plus:115}));
const {host,dom}=chart(values),groups=[...host.querySelectorAll('.viz-error-bars')];
const bars=i=>[...groups[i].querySelectorAll('rect')];
assert.deepEqual(bars(0).map(b=>b.dataset.series),['prediction','business_plan']);
assert.deepEqual(bars(0).map(b=>b.getAttribute('fill')),['#2563eb','#16a34a']);
assert.deepEqual(bars(1).map(b=>b.dataset.series),['business_plan','prediction']);
assert.deepEqual(bars(1).map(b=>b.getAttribute('fill')),['#eab308','#dc2626']);
for(const i of [0,1]){assert(Number(bars(i)[0].getAttribute('height'))>Number(bars(i)[1].getAttribute('height')));assert.equal(bars(i)[0].getAttribute('x'),bars(i)[1].getAttribute('x'));}
assert(Number(bars(3)[1].getAttribute('width'))<Number(bars(3)[0].getAttribute('width')));
assert.equal(bars(3)[0].getAttribute('height'),bars(3)[1].getAttribute('height'));
assert.equal(bars(5).length,0);assert.deepEqual(bars(6).map(b=>b.dataset.series),['business_plan']);assert.equal(bars(7)[0].dataset.difference,'-10');
for(const b of host.querySelectorAll('.viz-error-bar')){assert.equal(b.getAttribute('fill-opacity'),'1');for(const key of ['x','y','width','height'])assert(Number.isFinite(Number(b.getAttribute(key))));}
const readout=host.querySelector('.viz-readout');assert.equal(readout.children.length,2);assert([...readout.children].every(e=>e.tagName==='TABLE'));
assert.equal(readout.querySelector('.viz-demand-readout tbody').rows.length,2);
assert.equal(readout.querySelector('.viz-weather-readout tbody').rows.length,2);
const textRows=()=>[...readout.querySelector('.viz-demand-readout tbody').rows].map(r=>[...r.cells].map(c=>c.textContent));
assert.deepEqual(textRows()[0],['2026-01-01','예측값','130','100','30','30%','90','115']);
assert.deepEqual(textRows()[1],['계획량','110','100','10','10%','—','—']);
const svg=host.querySelector('.viz-stage svg');
svg.onfocus();svg.onkeydown({key:'ArrowRight',preventDefault(){}});
assert.equal(textRows()[0][4],'-5');assert.equal(textRows()[1][3],'-25');
assert.equal(host.querySelector('.viz-stage .viz-crosshair').getAttribute('x1'),host.querySelector('.viz-error-svg .viz-crosshair').getAttribute('x1'));
for(let i=0;i<3;i++)svg.onkeydown({key:'ArrowRight',preventDefault(){}});
assert.equal(textRows()[0][5],'—');assert.equal(textRows()[1][4],'—'); // GT=0: no percentage division
assert.equal(textRows()[1][3],'0');
dom.window.close();
const monthly=chart([
 {date:'2026-01-01',actual:100,prediction:110,business_plan:130,temp_avg:0,observed_temp_avg:2},
 {date:'2026-01-02',actual:100,prediction:90,business_plan:120,temp_avg:10,observed_temp_avg:4},
 {date:'2026-02-01',actual:100,prediction:110,business_plan:120,temp_avg:4},
 {date:'2026-02-02',actual:100,prediction:110,business_plan:null,temp_avg:8},
 {date:'2026-03-01',actual:100,prediction:110,business_plan:120},
 {date:'2026-03-02',actual:null,prediction:110,business_plan:120},
]);
[...monthly.host.querySelectorAll('button')].find(b=>b.textContent==='월별 합계').click();
const mg=[...monthly.host.querySelectorAll('.viz-error-bars')];
assert.equal(mg[0].querySelector('[data-series=business_plan]').dataset.difference,'50');
assert.equal(mg[1].querySelector('[data-series=business_plan]'),null);
assert.equal(mg[2].querySelectorAll('rect').length,0);
assert(monthly.host.querySelector('.viz-readout-date').textContent.includes('2026-01-01 ~ 2026-01-02'));
const wr=[...monthly.host.querySelectorAll('.viz-weather-readout tbody tr')];assert.equal(wr[0].cells[2].textContent,'5');assert.equal(wr[1].cells[2].textContent,'3');
monthly.dom.window.close();
for(const rows of [[],[{date:'2026-01-01',prediction:20,business_plan:30}], [{date:'2026-01-01',actual:10,prediction:null,business_plan:1000}]]){
 const c=chart(rows);assert.equal(!!c.host.querySelector('.viz-error-svg'),rows.length===1&&rows[0].actual===10);
 if(rows[0]?.actual===10){const rect=c.host.querySelector('.viz-error-bar');assert(Number(rect.getAttribute('y'))>=20);assert(Number(rect.getAttribute('y'))+Number(rect.getAttribute('height'))<=145);}
 c.dom.window.close();
}
console.log('PASS: two-row tables, temperature tables, sign colors, both overlap orders, ties, GT=0, missing inputs, shared cursor, monthly completeness and scaling');
