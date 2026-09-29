const {loadPyodide}=require('pyodide');const fs=require('fs'),path=require('path');
const {TreeBooster}=require('../booster.js');
process.chdir(__dirname);
fs.mkdirSync('.pyodide-cache',{recursive:true});
(async()=>{
const py=await loadPyodide({packageCacheDir:path.resolve('.pyodide-cache')});console.log('WASM initialized');
await py.loadPackage(['numpy','pandas','scipy','micropip']);console.log('WASM packages loaded');
await py.runPythonAsync('import micropip\nawait micropip.install(["holidays==0.80", "openpyxl==3.1.5"])');
py.FS.mkdirTree('/app/engine');py.FS.mkdirTree('/uploads');for(const name of fs.readdirSync('../engine').filter(n=>n.endsWith('.py')))py.FS.writeFile('/app/engine/'+name,fs.readFileSync('../engine/'+name));
const fixture=require('./fixtures/xgboost-parity.json'),booster=new TreeBooster(fixture.document,fixture.columns);globalThis.forecastPredict=rows=>JSON.stringify(booster.predict(JSON.parse(rows)));
py.FS.writeFile('/uploads/model.zip',fs.readFileSync('fixtures/test-model.zip'));py.FS.writeFile('/uploads/weather.csv',fs.readFileSync('fixtures/weather.csv'));
await py.runPythonAsync('import sys\nsys.path.insert(0,"/app")\nfrom engine.browser import load_model,predict_request\nload_model(\'["/uploads/model.zip"]\')');
console.log('WASM model loaded');const files={history:[],truth:[],plan:[],observed:[],weather:[{path:'/uploads/weather.csv',name:'weather.csv',mapping:{date:'date',temp_avg:'temp_avg',temp_max:'temp_max',temp_min:'temp_min'}}]};
const request={start:'2026-01-10',end:'2026-02-12',years:5,mc:2,delta:1.645,minus:1.645,plus:1.645,limit_history:true,use_stored_weather:false,climate_all:false,gt:false,files,climate_ranges:[]};
const result=JSON.parse(py.globals.get('predict_request')(JSON.stringify(request)));const expected=require('./fixtures/expected.json');
require('assert/strict').equal(result.records.length,expected.length);
for(let i=0;i<expected.length;i++)for(const key of Object.keys(expected[i]))require('assert/strict').ok(Math.abs(result.records[i][key]-expected[i][key])<1e-6, key+' '+i);
console.log('PASS actual WebAssembly: 34-day recursive + MC forecast matches native reference');
})();
