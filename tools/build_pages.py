"""Stage only browser runtime source and registered model assets for Pages."""
import json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'_site'
if out.exists():shutil.rmtree(out)
out.mkdir()
for name in ['index.html','app.js','worker.js','booster.js','style.css','charts.js','charts.css','.nojekyll']:
    shutil.copy2(root/name,out/name)
shutil.copytree(root/'engine',out/'engine',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
models=out/'storage/models';models.mkdir(parents=True)
manifest=root/'storage/models/manifest.json';shutil.copy2(manifest,models/'manifest.json')
for item in json.loads(manifest.read_text()):
    source=root/'storage/models'/item['directory'];dest=models/item['directory'];dest.mkdir()
    for name in ['model.json','config.json','climate_history.csv']:shutil.copy2(source/name,dest/name)
print(f'Pages ready: {out}; {sum(p.stat().st_size for p in out.rglob("*") if p.is_file()):,} bytes')
