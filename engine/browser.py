"""Prediction-only browser adapter; no training, HTTP server or GPU required."""
import io, json, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from .models import Forecaster
from .preprocessing import normalize, read_table, load_daily, load_weather, load_ground_truth, TEMP, ALIASES
from .scenarios import forecast_scenarios
from .evaluation import summarize_prediction

model = None

def inspect_file(path):
    raw=read_table(path)
    raw.columns=raw.columns.astype(str).str.strip()
    if raw.columns.duplicated().any(): raise ValueError('파일에 중복 컬럼명이 있습니다.')
    columns=list(raw.columns)
    return json.dumps({'columns':columns,'rows':len(raw),'mapping':{k:next((c for c in aliases if c in columns),'') for k,aliases in ALIASES.items()}},ensure_ascii=False)

def load_model(paths_json):
    global model
    model=None
    paths=json.loads(paths_json)
    required=['config.json','model.json','climate_history.csv']
    if len(paths)==1 and paths[0].lower().endswith('.zip'):
        with zipfile.ZipFile(paths[0]) as z:
            files={}
            for name in required:
                matches=[i for i in z.infolist() if not i.is_dir() and Path(i.filename).name==name and not i.filename.startswith('__MACOSX/')]
                if len(matches)!=1:raise ValueError(f'ZIP 안에 {name} 파일이 정확히 하나 필요합니다.')
                if matches[0].file_size>100*1024**2:raise ValueError('모델 개별 파일은 100MB 이하로 준비하세요.')
                files[name]=z.read(matches[0])
    else:
        files={Path(p).name:Path(p).read_bytes() for p in paths}
        if any(n not in files for n in required):raise ValueError('config.json, model.json, climate_history.csv를 함께 선택하세요.')
    meta=json.loads(files['config.json'].decode('utf-8-sig'))
    config=meta.get('config',{})
    if meta.get('mode')!='weather' or not isinstance(meta.get('feature_cols'),list) or not meta['feature_cols']:
        raise ValueError('weather 모델의 config와 feature_cols가 필요합니다.')
    if meta.get('target') not in ['normal','chp'] or config.get('target')!=meta['target']:
        raise ValueError('모델 대상(normal/chp) 메타데이터가 일치하지 않습니다.')
    if config.get('target_transform') not in ['log1p','seasonal_log_ratio']:raise ValueError('지원하지 않는 target_transform입니다.')
    for key,low,high in [('window_size',7,3660),('horizon',1,366)]:
        if not isinstance(config.get(key),int) or not low<=config[key]<=high:raise ValueError(f'{key} 설정을 확인하세요.')
    for key in ['lags','rolling_windows','base_temp_hdd','base_temp_cdd']:
        if key not in config:raise ValueError(f'config에 {key}가 필요합니다.')
    trained=pd.Timestamp(meta['trained_through'])
    if pd.isna(trained):raise ValueError('모델 기준일이 필요합니다.')
    hist=normalize(pd.read_csv(io.BytesIO(files['climate_history.csv']),encoding='utf-8-sig'))
    if any(c not in hist for c in ['target']+TEMP):raise ValueError('climate_history에 수요·평균·최고·최저 기온 컬럼이 필요합니다.')
    if 'target_observed' in hist:
        flags=hist.target_observed.astype(str).str.lower()
        if not flags.isin(['true','false','1','0']).all():raise ValueError('target_observed는 true/false여야 합니다.')
        hist['target_observed']=flags.isin(['true','1'])
    else:hist['target_observed']=hist.target.notna()
    hist=hist[hist.date<=trained].copy()
    if hist.empty:raise ValueError('모델 기준일 이전의 이력이 없습니다.')
    candidate=Forecaster(config,'weather');candidate.meta=meta;candidate.columns=meta['feature_cols'];candidate.climate_history=hist
    from js import forecastPredict
    def predict(x):
        rows=pd.DataFrame(x).to_json(orient='values',double_precision=15)
        return json.loads(forecastPredict(rows))
    candidate.model=predict
    model=candidate
    return json.dumps({'meta':meta,'document':json.loads(files['model.json'].decode('utf-8-sig'))},ensure_ascii=False)

def read_inputs(items, role):
    frames=[]
    for item in items:
        mapping=item['mapping']
        required=['date']+(['target'] if role in ['history','truth','plan'] else [])
        if any(not mapping.get(k) for k in required):raise ValueError(f'{role}: 날짜/수요 컬럼을 지정하세요.')
        chosen={source:dest for dest,source in mapping.items() if source}
        if len(chosen)!=sum(bool(v) for v in mapping.values()):raise ValueError('한 컬럼을 여러 항목에 중복 지정할 수 없습니다.')
        raw=read_table(item['path']);raw.columns=raw.columns.astype(str).str.strip()
        table=normalize(raw[list(chosen)].rename(columns=chosen))
        if item.get('start'):table=table[table.date>=pd.Timestamp(item['start'])]
        if item.get('end'):table=table[table.date<=pd.Timestamp(item['end'])]
        if item.get('start') and item.get('end') and item['start']>item['end']:raise ValueError('파일 적용 시작일이 종료일보다 늦습니다.')
        for col in TEMP:
            if col not in table:table[col]=np.nan
        for col in TEMP:
            if ((table[col]<-60)|(table[col]>60)).any():raise ValueError('기온은 -60~60°C 범위여야 합니다.')
        if ((table.temp_min>table.temp_max)|(table.temp_min>table.temp_avg)|(table.temp_avg>table.temp_max)).any():raise ValueError('최저 ≤ 평균 ≤ 최고 기온 관계를 확인하세요.')
        frames.append(table)
    if not frames:return None
    return pd.concat(frames,ignore_index=True).drop_duplicates('date',keep='last').sort_values('date').reset_index(drop=True)

def predict_request(request_json):
    if model is None:raise ValueError('모델을 먼저 불러오세요.')
    p=json.loads(request_json)
    start,end=pd.Timestamp(p['start']),pd.Timestamp(p['end'])
    if pd.isna(start) or pd.isna(end) or start>end:raise ValueError('예측 시작일·종료일을 확인하세요.')
    raw=read_inputs(p['files']['history'],'history')
    if raw is None:raw=model.climate_history.copy()
    cutoff=min(start-pd.Timedelta(days=1),pd.Timestamp(model.meta['trained_through'])) if p['limit_history'] else start-pd.Timedelta(days=1)
    observed=raw[raw.target.notna() & (raw.date<=cutoff)].copy()
    history,_=load_daily(observed,missing_target='error')
    if 'target_observed' in observed:
        flags=observed.set_index('date').target_observed
        history['target_observed']=flags.reindex(pd.DatetimeIndex(history.date)).to_numpy(dtype=bool)
    origin=history.date.max()
    if origin<pd.Timestamp(model.meta['trained_through']):raise ValueError('입력 이력이 모델 기준일까지 있어야 합니다.')
    if (end-origin).days>3660:raise ValueError('origin 이후 최대 3,660일까지 예측할 수 있습니다.')
    dates=pd.date_range(start,end);full=pd.date_range(origin+pd.Timedelta(days=1),end)
    weather_input=read_inputs(p['files']['weather'],'weather')
    if p['use_stored_weather']:
        stored=raw[['date']+TEMP]
        weather_input=stored if weather_input is None else pd.concat([stored,weather_input]).drop_duplicates('date',keep='last')
    weather=load_weather(weather_input,full,allow_missing=True) if weather_input is not None and not weather_input.empty else None
    if p['climate_all']:weather=None
    elif p['climate_ranges']:
        if weather is None:weather=pd.DataFrame(np.nan,index=full,columns=TEMP)
        for r in p['climate_ranges']:
            a,b=pd.Timestamp(r['start']),pd.Timestamp(r['end'])
            if pd.isna(a) or pd.isna(b) or a>b:raise ValueError('N개년 적용 구간을 확인하세요.')
            weather.loc[(weather.index>=a)&(weather.index<=b),TEMP]=np.nan
    # Comparison-only data are never passed to the predictor.
    result=forecast_scenarios(model,history,dates,weather,dict(auto_years=False,auto_delta=False,
        climate_years=p['years'],mc_samples=p['mc'],delta=p['delta'],delta_unit='celsius',
        delta_minus=p['minus'],delta_plus=p['plus'],latitude=37.5665))
    attrs=dict(result.attrs)
    metrics=None
    if p['gt']:
        truth=read_inputs(p['files']['truth'],'truth')
        if truth is None:truth=raw[raw.target.notna()]
        truth=load_ground_truth(truth,dates)
        if not truth.actual.notna().any():raise ValueError('GT에 예측 기간과 겹치는 수요가 없습니다.')
        result=result.merge(truth,on='date',how='left')
        metrics,_=summarize_prediction(result)
    for role in ['plan','observed']:
        extra=read_inputs(p['files'][role],role)
        if extra is not None:
            extra=extra.set_index('date').reindex(dates)
            if role=='plan':
                if (extra.target<0).any():raise ValueError('계획량은 음수일 수 없습니다.')
                result['business_plan']=extra.target.to_numpy()
            else:
                for c in TEMP:result['observed_'+c]=extra[c].to_numpy()
    result['origin']=origin;result['target']=model.meta['target'];result['lead']=result.overall_lead
    for c in ['date','block_origin','origin']:result[c]=pd.to_datetime(result[c]).dt.strftime('%Y-%m-%d')
    metadata={'name':'수요예측 모델','target':model.meta['target'],'trained_through':model.meta['trained_through'],
              'origin':str(origin.date()),'start':p['start'],'end':p['end'],'scenarios':attrs.get('scenario_metadata'),
              'comparison_inputs':'joined_after_inference','settings':{k:v for k,v in p.items() if k!='files'},
              'files':{k:[{x:y for x,y in f.items() if x!='path'} for f in v] for k,v in p['files'].items()}}
    monthly=pd.DataFrame(attrs.get('scenario_monthly',[]))
    grouped=result.assign(month=result.date.str[:7]).groupby('month')
    monthly['days']=monthly.month.map(grouped.size())
    for col in ['actual','business_plan']:
        if col in result:
            totals=grouped[col].agg(lambda x:x.sum(min_count=len(x)))
            monthly[col]=monthly.month.map(totals)
    return json.dumps({'records':json.loads(result.to_json(orient='records')),'csv':result.to_csv(index=False),
                       'monthly_csv':monthly.to_csv(index=False),
                       'bridge_csv':pd.DataFrame(attrs.get('bridge_predictions',[])).to_csv(index=False),
                       'metrics':metrics,'metadata':metadata},ensure_ascii=False,allow_nan=False)
