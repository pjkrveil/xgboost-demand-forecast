# 수요예측 모델 — 모델 3개 포함 GitHub Pages 배포본

**별도의 예측 서버 없이, 사이트에 접속한 PC의 CPU·메모리를 사용하여 예측합니다.**
GitHub Pages는 화면·코드·모델 파일을 전달하고, 예측 계산은 브라우저의 Web Worker와 WebAssembly에서 실행합니다. 이용자 PC에 Python, Docker, XGBoost, GPU 드라이버를 설치할 필요가 없습니다.

## 바로 업로드하기

1. 이 ZIP을 해제합니다.
2. `forecast-github-pages` 폴더 **안의 내용**을 GitHub 저장소 루트에 업로드합니다. 저장소 루트에 `index.html`, `app.js`, `storage/`가 있어야 합니다. ZIP 파일 자체를 업로드하면 실행되지 않습니다.
3. 저장소 **Settings → Pages → Build and deployment**에서 아래 중 하나를 선택합니다.

### 간단한 방법: 브랜치에서 게시

- Source: **Deploy from a branch**
- Branch: **main**
- Folder: **/(root)**
- **Save** 후 Pages에 표시되는 주소에 접속합니다.

`.nojekyll`을 포함하세요. 기본 브랜치 이름이 `main`이 아니면 실제 브랜치를 선택합니다. GitHub 웹 화면에서 여러 파일을 업로드할 경우 모델 폴더도 빠짐없이 포함하고, 한 번에 선택하는 파일 수가 많으면 나누어 업로드하세요.

### 자동 검증 후 게시: GitHub Actions

- 숨김 폴더 `.github/workflows/pages.yml`까지 업로드합니다.
- Settings → Pages → Source: **GitHub Actions**
- `main`에 커밋하거나 Actions의 **Deploy demand forecast to GitHub Pages → Run workflow**를 실행합니다.

이 방법은 `tools/build_pages.py`로 화면·실행 코드·필수 모델 파일만 `_site/`에 모아 게시합니다. 테스트·안내·기존 평가 산출물은 웹사이트 배포에서 제외됩니다. 소스의 `storage/models/`에는 첨부의 모든 원본 파일이 보존됩니다.

게시 주소는 보통 `https://사용자명.github.io/저장소명/`입니다. 모든 리소스 경로를 상대 경로로 작성하여 저장소 하위 주소에서도 작동합니다. GitHub에 실제 업로드하거나 게시한 상태는 아닙니다.

## 사용 방법

1. 왼쪽 **사이트에 등록된 모델**에서 원하는 모델을 선택합니다.
2. **등록 모델 불러오기**를 누릅니다. 선택한 모델만 다운로드하여 메모리에 올립니다.
3. 예측 시작일·종료일을 지정합니다. 기본 시작일은 모델 기준일 다음 날인 `2026-01-01`입니다.
4. 필요하면 과거 이력, 미래 기온, 비교용 GT, 사업 계획, 비교용 실측 기온 CSV/XLSX를 불러옵니다.
5. N개년, Monte Carlo 횟수, ±기온 변화량을 설정하고 **수요 예측 시작**을 누릅니다.
6. 일별·월별 차트와 CSV/JSON 결과를 확인합니다.

과거 이력을 따로 선택하지 않으면 해당 모델의 `climate_history.csv`를 사용합니다. 예측 기온이 없는 날짜는 모델의 기온 이력에서 N개년 통계로 보완합니다. GT·계획·비교용 기온은 추론 후 비교에만 사용합니다.

## 포함된 모델

| 화면 이름 | 원본 폴더 | 대상 | 모델 기준일 | weight 크기 |
|---|---|---|---|---:|
| 일반 사입량 · 768b0664 | `768b06646be1496f9bb9990fbc536bb7` | 일반 | 2025-12-31 | 4,206,512 bytes |
| 열병합 포함 사입량 · 3a1903ab | `3a1903abca1645fcb774dbc2fd4a32b6` | 열병합 포함 | 2025-12-31 | 4,214,958 bytes |
| 일반 사입량 · f45d2350 | `xgboost-normal-f45d2350` | 일반 | 2025-12-31 | 4,211,589 bytes |

각 모델은 2,000개 트리, 입력 특성 116개, 과거 window 365일, 블록 horizon 31일입니다. 모델을 재학습하거나 변환하지 않고 XGBoost가 저장한 원본 JSON을 그대로 읽습니다.

```text
index.html
app.js
worker.js
booster.js
engine/
storage/
  models/
    manifest.json
    768b06646be1496f9bb9990fbc536bb7/
      model.json
      config.json
      climate_history.csv
      feature_importance.csv
    3a1903abca1645fcb774dbc2fd4a32b6/
      ...
    xgboost-normal-f45d2350/
      ...
```

첨부 `models.zip`의 실제 파일 형식은 gzip으로 압축한 tar였습니다. 형식을 판별해 해제했으며, 포함된 원본 파일 21개를 모두 보존했습니다. 화면 목록을 위한 `manifest.json`만 추가했습니다.

## 실행 환경과 데이터

- **예측 계산:** 접속한 PC의 CPU·메모리. GPU/CUDA와 예측 API 서버를 사용하지 않습니다.
- **첫 실행 다운로드:** 선택 모델 약 4.2MB와 기온 이력, Pyodide 실행 환경·Python 패키지를 내려받습니다. 전체 초기 다운로드 용량은 모델 크기보다 큽니다.
- **외부 배포 경로:** Pyodide 0.28.3은 jsDelivr, `holidays==0.80`·`openpyxl==3.1.5`는 PyPI에서 로드합니다. 첫 로딩에는 해당 도메인에 접속할 수 있어야 합니다. 완전 오프라인 패키지는 아닙니다.
- **입력 파일:** 브라우저에서 읽고 계산하며 예측 서버로 전송하지 않습니다.
- **모델 공개 범위:** 사이트에 배치한 모델과 포함된 수요·기온 이력은 방문자가 다운로드할 수 있습니다. 이 앱은 모델 파일을 숨기는 구조가 아닙니다.
- **작업 보관:** 모델·입력·결과는 브라우저 세션 메모리에 유지됩니다. 새로고침 전 필요한 결과를 다운로드하세요.
- **속도:** PC 성능, 예측 기간, Monte Carlo 횟수에 따라 달라집니다. 긴 작업은 중지할 수 있습니다. 중지하면 모델과 입력을 다시 불러와야 합니다.
- **기능:** 학습·legacy/LSTM 기능은 제외했습니다. 원본 서버의 공용 DB, 작업 큐, 이력 버전 관리는 제공하지 않습니다.
- **시나리오:** ±delta는 °C, MC 범위는 σ입니다. 기온 시나리오 범위는 전체 수요예측 오차의 신뢰구간이 아닙니다.

## 내 PC에서 미리 보기

이 단계의 Python은 개발용 정적 파일 서버에만 필요하며, 게시된 사이트의 이용자는 설치할 필요가 없습니다.

```bash
python -m http.server 8000
```

http://localhost:8000 에 접속합니다. `index.html`을 더블클릭하는 `file://` 실행은 지원하지 않습니다.

## 모델 추가

한 모델 폴더 또는 그 폴더의 ZIP을 등록할 수 있습니다.

```bash
python tools/register_model.py /path/to/model.zip --id my-model --name "표시 이름"
```

기존 등록 모델의 이름은 `storage/models/manifest.json`의 `name`을 바꿉니다. 폴더를 바꾸면 `directory`도 함께 수정하세요.

## 검증 재실행

```bash
node tests/booster.test.cjs
python tests/check_site.py
cd tests
npm install
npm run test:models
```

마지막 명령은 첨부된 실제 모델 3개를 WebAssembly에서 실행해 원본 XGBoost 결과와 비교합니다. 상세 결과와 확인하지 못한 범위는 `VALIDATION.md`에 있습니다.

## 공식 문서

- [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [GitHub 파일 크기 제한](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
- [GitHub Pages Actions 배포](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [Pyodide Web Worker](https://pyodide.org/en/0.28.3/usage/webworker.html)
