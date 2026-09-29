from pathlib import Path
import ast,json,re
root=Path(__file__).resolve().parents[1]
for path in (root/'engine').glob('*.py'):
    tree=ast.parse(path.read_text())
    assert not any(isinstance(n,ast.FunctionDef) and n.name in ['fit','train','training_matrix'] for n in ast.walk(tree)),path
    assert not re.search(r'^\s*(?:from|import) (flask|xgboost|torch|sklearn)',path.read_text(),re.M),path
for file in ['index.html','app.js','worker.js']:
    text=(root/file).read_text()
    assert not re.search(r'/(?:hub|legacy)/',text),file
html=(root/'index.html').read_text()
assert '<title>수요예측 모델</title>' in html
for ref in re.findall(r'(?:src|href)="(\./[^"#]+)"',html):assert (root/ref.split("?",1)[0]).exists(),ref
for item in json.loads((root/'storage/models/manifest.json').read_text()):
    assert re.fullmatch(r'[a-zA-Z0-9_-]+',item['directory'])
    for name in ['model.json','config.json','climate_history.csv']:assert (root/'storage/models'/item['directory']/name).is_file()
print('PASS: static paths, prediction-only modules, model manifest')
