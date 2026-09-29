"""Strict daily schema; causal target filling; no fitted full-series transforms."""
from pathlib import Path
import numpy as np
import pandas as pd

ALIASES = {
    'date': ['date', '일자', '날짜', '일시'],
    'target': ['target', 'gas_usage', '사입량', '수요', '사용량'],
    'temp_avg': ['temp_avg', 'avg_temp', '평균온도', '평균기온', '평균기온(℃)'],
    'temp_max': ['temp_max', 'max_temp', '최고온도', '최고기온', '최고기온(℃)'],
    'temp_min': ['temp_min', 'min_temp', '최저온도', '최저기온', '최저기온(℃)'],
}
TEMP = ['temp_avg', 'temp_max', 'temp_min']

def read_table(path):
    path = Path(path)
    if path.suffix.lower() == '.xlsx':
        return pd.read_excel(path, engine='openpyxl')
    if path.suffix.lower() != '.csv':
        raise ValueError('CSV 또는 XLSX 파일을 사용하세요.')
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('CSV 인코딩은 UTF-8 또는 CP949여야 합니다.')

def normalize(table, mapping=None):
    table = table.copy()
    table.columns = table.columns.astype(str).str.strip()
    if mapping:
        table = table.rename(columns=mapping)
    for name, aliases in ALIASES.items():
        if name not in table:
            matches = [a for a in aliases if a in table]
            if len(matches) > 1:
                raise ValueError(f'{name} 컬럼이 모호합니다: {matches}')
            if matches:
                table = table.rename(columns={matches[0]: name})
    if table.columns.duplicated().any():
        raise ValueError('중복 컬럼명은 허용하지 않습니다.')
    if 'date' not in table:
        raise ValueError('date/일자 컬럼이 필요합니다.')
    dates = table.date.astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    dates = pd.to_datetime(dates, format='mixed', errors='coerce')
    if dates.isna().any():
        raise ValueError('해석할 수 없는 날짜가 있습니다. YYYY-MM-DD를 사용하세요.')
    if dates.dt.tz is not None or (dates != dates.dt.normalize()).any():
        raise ValueError('시간대/시각 없이 일 단위 날짜를 사용하세요.')
    table['date'] = dates
    if dates.duplicated().any():
        raise ValueError('중복 날짜가 있습니다. 일별 집계 후 입력하세요.')
    for col in ['target'] + TEMP:
        if col in table:
            s = table[col].astype(str).str.replace(',', '', regex=False).str.strip()
            numeric = pd.to_numeric(s, errors='coerce')
            bad = numeric.isna() & table[col].notna() & ~s.isin(['', '-', 'nan', 'None'])
            if bad.any() or np.isinf(numeric).any():
                raise ValueError(f'{col}: 숫자 형식 오류 또는 무한대가 있습니다.')
            table[col] = numeric
    return table.sort_values('date').reset_index(drop=True)

def clean_temperature(table, strict=False):
    table = table.copy()
    for col in TEMP:
        if col not in table:
            table[col] = np.nan
    # Optional extrema must not erase a valid supplied average.
    invalid = (table[TEMP] < -60) | (table[TEMP] > 60)
    if strict and invalid.temp_avg.any():
        raise ValueError('평균기온이 허용 범위(-60~60°C)를 벗어났습니다.')
    bad = invalid.any(axis=1)
    table[TEMP] = table[TEMP].mask(invalid)
    bad_min, bad_max = table.temp_min > table.temp_avg, table.temp_max < table.temp_avg
    table.loc[bad_min, 'temp_min'] = np.nan
    table.loc[bad_max, 'temp_max'] = np.nan
    reversed_pair = table.temp_min > table.temp_max
    table.loc[reversed_pair, ['temp_min','temp_max']] = np.nan
    bad |= bad_min | bad_max | reversed_pair
    return table, int(bad.sum())

def load_daily(path, mapping=None, missing_target='error', cutoff=None):
    table = normalize(read_table(path) if not isinstance(path, pd.DataFrame) else path, mapping)
    if cutoff is not None:
        table = table[table.date <= pd.Timestamp(cutoff)].copy()
    if table.empty or 'target' not in table:
        raise ValueError('과거 date, target 데이터가 필요합니다.')
    if (table.target < 0).any():
        raise ValueError('음수 사입량은 허용하지 않습니다.')
    original_rows = len(table)
    table = table.set_index('date').reindex(pd.date_range(table.date.min(), table.date.max(), freq='D'))
    table.index.name = 'date'
    table = table.reset_index()
    observed = table.target.notna()
    missing = int((~observed).sum())
    if missing and missing_target == 'error':
        raise ValueError(f'수요/날짜 결측 {missing}건. 원본을 보완하거나 --missing-target ffill을 지정하세요.')
    if missing_target not in ('error', 'ffill'):
        raise ValueError('missing_target must be error or ffill')
    table['target_observed'] = observed
    if missing_target == 'ffill':
        table['target'] = table.target.ffill()
    if table.target.isna().any():
        raise ValueError('선두 수요 결측은 과거 값으로 채울 수 없습니다.')
    table, invalid = clean_temperature(table)
    report = {'input_rows': original_rows, 'daily_rows': len(table),
              'start': str(table.date.min().date()), 'end': str(table.date.max().date()),
              'missing_target_days': missing, 'invalid_temperature_days': invalid,
              'temperature_missing': table[TEMP].isna().sum().to_dict(),
              'missing_target_policy': missing_target}
    return table, report

def prepare_forecast_weather(table):
    """Validate inputs; defer missing averages until model history is available."""
    if table.empty:
        raise ValueError('예측 기온 데이터가 비어 있습니다.')
    table, _ = clean_temperature(table, strict=True)
    derived = table.temp_avg.isna() & table.temp_min.notna() & table.temp_max.notna()
    table['temp_avg_source'] = 'provided_average'
    table.loc[derived, 'temp_avg_source'] = 'pending_weighted_average'
    invalid = table.temp_avg.isna() & ~derived
    if invalid.any():
        missing = table.loc[invalid, 'date'].dt.strftime('%Y-%m-%d').tolist()
        raise ValueError(f'예측 평균기온이 누락되었고 유효한 최고·최저 기온 쌍도 없습니다: {missing[:10]}')
    return table

def load_weather(path, dates, bridge_before=None, allow_missing=False):
    table = normalize(read_table(path) if not isinstance(path, pd.DataFrame) else path)
    for col in TEMP:
        if col not in table:
            table[col] = np.nan
    table = table.set_index('date').reindex(pd.DatetimeIndex(dates)).rename_axis('date').reset_index()
    if allow_missing:
        table,_=clean_temperature(table,strict=True)
        usable=table.temp_avg.notna() | (table.temp_min.notna() & table.temp_max.notna())
        table['temp_avg_source']='automatic_climatology'
        if usable.any():
            prepared=prepare_forecast_weather(table.loc[usable].copy())
            table.loc[usable,prepared.columns]=prepared
        table.loc[~usable,TEMP]=np.nan
    elif bridge_before is not None:
        table['temp_avg_source'] = ''
        # Only entirely absent bridge weather may use climatology. Invalid
        # supplied values and missing requested-period weather remain errors.
        bridge = table.date.lt(pd.Timestamp(bridge_before)) & table[TEMP].isna().all(axis=1)
        supplied = prepare_forecast_weather(table.loc[~bridge].copy())
        table.loc[~bridge, supplied.columns] = supplied
        table.loc[bridge, 'temp_avg_source'] = 'bridge_climatology'
    else:
        table = prepare_forecast_weather(table)
    return table.set_index('date')[TEMP + ['temp_avg_source']]

def load_ground_truth(path, dates=None):
    table = normalize(read_table(path) if not isinstance(path, pd.DataFrame) else path)
    if 'target' not in table:
        raise ValueError('GT 파일에 date,target 컬럼이 필요합니다.')
    if table.target.isna().any():
        raise ValueError('GT target에는 빈 값이 없어야 합니다.')
    if (table.target < 0).any():
        raise ValueError('GT target에 음수 사입량은 허용하지 않습니다.')
    result = table[['date', 'target']].rename(columns={'target': 'actual'})
    if dates is None:
        return result
    dates = pd.DatetimeIndex(dates)
    return result.set_index('date').reindex(dates).rename_axis('date').reset_index()
