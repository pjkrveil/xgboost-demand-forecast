/* All Python computation stays in a worker so charts and cancellation respond. */
importScripts('./booster.js');
let py=null, engine=null, ready=null, initialized=false;
globalThis.forecastPredict=(rows)=>JSON.stringify(engine.predict(JSON.parse(rows)));
const progress=text=>postMessage({progress:text});
async function boot(){
  if(ready)return ready;
  ready=(async()=>{
    progress('예측 실행 환경을 준비합니다. 첫 실행은 수십 초 이상 걸릴 수 있습니다.');
    const url='https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
    importScripts(url+'pyodide.js');
    py=await loadPyodide({indexURL:url});
    await py.loadPackage(['numpy','pandas','scipy','micropip']);
    progress('한국 공휴일 데이터를 준비합니다.');
    await py.runPythonAsync('import micropip\nawait micropip.install(["holidays==0.80", "openpyxl==3.1.5"])');
    py.FS.mkdirTree('/app/engine');py.FS.mkdirTree('/uploads');
    const names=['__init__','features','models','scenarios','preprocessing','temperature_weighting','evaluation','browser'];
    await Promise.all(names.map(async name=>{
      const response=await fetch('./engine/'+name+'.py');if(!response.ok)throw Error('예측 코드 로딩 실패: '+name);
      py.FS.writeFile('/app/engine/'+name+'.py',await response.text());
    }));
    await py.runPythonAsync('import sys\nsys.path.insert(0,"/app")\nfrom engine.browser import inspect_file, load_model, predict_request');
    initialized=true;progress('예측 실행 환경이 준비되었습니다.');
  })();
  return ready;
}
let queue=Promise.resolve();
onmessage=e=>{queue=queue.then(async()=>{
 const {id,action,payload}=e.data;
 try{
  await boot();let result;
  if(action==='upload'){
    const path='/uploads/'+payload.id+'/'+payload.name.replace(/[^a-zA-Z0-9_.-]/g,'_');
    py.FS.mkdirTree('/uploads/'+payload.id);py.FS.writeFile(path,new Uint8Array(payload.bytes));
    if(payload.inspect){const f=py.globals.get('inspect_file');try{result=JSON.parse(f(path));}finally{f.destroy();}}
    result={...result,path};
  }else if(action==='model'){
    engine=null;progress('모델 구조와 입력 설정을 확인합니다.');
    const fn=py.globals.get('load_model');let bundle;
    try{bundle=JSON.parse(fn(JSON.stringify(payload)));}finally{fn.destroy();}
    engine=new TreeBooster(bundle.document,bundle.meta.feature_cols);
    result={...bundle.meta,tree_count:engine.trees.length};
  }else if(action==='predict'){
    if(!engine)throw Error('유효한 모델을 먼저 불러오세요.');
    progress('수요를 예측합니다. 기간과 Monte Carlo 횟수에 따라 수 분 걸릴 수 있습니다.');
    const fn=py.globals.get('predict_request');try{result=JSON.parse(fn(JSON.stringify(payload)));}finally{fn.destroy();}
  }else throw Error('알 수 없는 작업입니다.');
  postMessage({id,result});
 }catch(err){const message=(err.message||String(err)).trim().split('\n').filter(Boolean).pop();postMessage({id,error:message,fatal:!initialized});}
});};
