"""Copy one existing forecast model into the static site. No training."""
import argparse,json,re,zipfile
from pathlib import Path
p=argparse.ArgumentParser(description='수요예측 사이트에 기존 모델 등록')
p.add_argument('source',type=Path);p.add_argument('--id',required=True);p.add_argument('--name',required=True)
a=p.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_-]+',a.id):p.error('--id는 영문/숫자/_/-만 가능합니다.')
root=Path(__file__).resolve().parents[1]/'storage/models';dest=root/a.id
if dest.exists():p.error('같은 id 폴더가 이미 있습니다. 다른 id를 사용하세요.')
required=['config.json','model.json','climate_history.csv'];files={}
if a.source.is_dir():
    for name in required:files[name]=(a.source/name).read_bytes()
else:
    with zipfile.ZipFile(a.source) as z:
        for name in required:
            matches=[i for i in z.infolist() if not i.is_dir() and Path(i.filename).name==name and not i.filename.startswith('__MACOSX/')]
            if len(matches)!=1 or matches[0].file_size>100*1024**2:p.error(f'{name} 파일이 정확히 하나 필요하며 100MB 이하여야 합니다.')
            files[name]=z.read(matches[0])
meta=json.loads(files['config.json'].decode('utf-8-sig'));model=json.loads(files['model.json'].decode('utf-8-sig'))
if meta.get('mode')!='weather' or meta.get('target') not in ['normal','chp'] or not meta.get('feature_cols'):p.error('weather 수요예측 모델의 메타데이터가 필요합니다.')
l=model.get('learner',{})
if l.get('gradient_booster',{}).get('name')!='gbtree' or l.get('objective',{}).get('name')!='reg:squarederror':p.error('수치형 gbtree 회귀 모델만 지원합니다.')
manifest=root/'manifest.json';items=json.loads(manifest.read_text())
if any(i['directory']==a.id for i in items):p.error('같은 id가 목록에 있습니다.')
dest.mkdir(parents=True)
for name,content in files.items():(dest/name).write_bytes(content)
items.append({'name':a.name,'directory':a.id})
manifest.write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'{a.name}: {dest} 등록 완료. storage/models/의 파일들은 게시 시 방문자가 다운로드할 수 있습니다.')
