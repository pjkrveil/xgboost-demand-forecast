/* Runs every supplied operating model in actual WebAssembly, no model training. */
const {loadPyodide}=require('pyodide');
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto');
const {TreeBooster}=require('../booster.js');
process.chdir(__dirname);fs.mkdirSync('.pyodide-cache',{recursive:true});
(async()=>{
 const py=await loadPyodide({packageCacheDir:path.resolve('.pyodide-cache')});
 await py.loadPackage(['numpy','pandas','scipy','micropip']);
 await py.runPythonAsync('import micropip\nawait micropip.install(["holidays==0.80", "openpyxl==3.1.5"])');
 py.FS.mkdirTree('/app/engine');py.FS.mkdirTree('/uploads');
 for(const name of fs.readdirSync('../engine').filter(n=>n.endsWith('.py')))py.FS.writeFile('/app/engine/'+name,fs.readFileSync('../engine/'+name));
 let booster;globalThis.forecastPredict=rows=>JSON.stringify(booster.predict(JSON.parse(rows)));
 await py.runPythonAsync('import sys\nsys.path.insert(0,"/app")\nfrom engine.browser import load_model,predict_request');
 const refs=require('./fixtures/registered-reference.json');
 const entries=JSON.parse(fs.readFileSync('../storage/models/manifest.json','utf8'));let report=[];
 for(const entry of entries){
  const directory=entry.directory,base='../storage/models/'+directory,reference=refs[directory];assert(reference,'Missing reference '+directory);
  const bytes=fs.readFileSync(base+'/model.json');assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),reference.model_sha256);
  const paths=[];for(const name of ['config.json','model.json','climate_history.csv']){const file='/uploads/'+name;py.FS.writeFile(file,fs.readFileSync(base+'/'+name));paths.push(file);}
  const load=py.globals.get('load_model');let bundle;try{bundle=JSON.parse(load(JSON.stringify(paths)));}finally{load.destroy();}
  booster=new TreeBooster(bundle.document,bundle.meta.feature_cols);
  const files={history:[],weather:[],truth:[],plan:[],observed:[]};
  const request={start:'2026-01-10',end:'2026-02-12',years:5,mc:2,delta:1.645,minus:1.645,plus:1.645,limit_history:true,use_stored_weather:false,climate_all:true,gt:false,files,climate_ranges:[]};
  const start=performance.now(),predict=py.globals.get('predict_request');let result;try{result=JSON.parse(predict(JSON.stringify(request)));}finally{predict.destroy();}
  assert.equal(result.records.length,reference.rows.length);let maximum=0;
  for(let i=0;i<reference.rows.length;i++)for(const [key,expected]of Object.entries(reference.rows[i])){
   const actual=result.records[i][key],error=Math.abs(actual-expected);maximum=Math.max(maximum,error);assert(Number.isFinite(actual));assert(error<Math.max(0.01,Math.abs(expected)*1e-7),`${directory} ${key} row ${i}: ${error}`);
  }
  report.push({directory,days:result.records.length,trees:booster.trees.length,max_absolute_error:maximum,seconds:(performance.now()-start)/1000});
  console.log('PASS registered WebAssembly model',JSON.stringify(report.at(-1)));
 }
 if(process.env.FORECAST_QA_REPORT)fs.writeFileSync(process.env.FORECAST_QA_REPORT,JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
