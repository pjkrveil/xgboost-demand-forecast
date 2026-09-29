"""Origin/window-based tabular features shared by training and inference."""
from functools import lru_cache
import holidays
import numpy as np
import pandas as pd

@lru_cache(maxsize=128)
def kr_holidays(year):
    return holidays.country_holidays('KR', years=[year-1, year, year+1])

def calendar(date):
    date = pd.Timestamp(date)
    hol = kr_holidays(date.year)
    doy = date.dayofyear
    return {'year': date.year, 'month': date.month, 'day': date.day, 'dow': date.dayofweek,
            'is_weekend': int(date.dayofweek >= 5), 'is_holiday': int(date.date() in hol),
            'before_holiday': int((date + pd.Timedelta(days=1)).date() in hol),
            'after_holiday': int((date - pd.Timedelta(days=1)).date() in hol),
            'doy_sin': np.sin(2*np.pi*doy/365.25), 'doy_cos': np.cos(2*np.pi*doy/365.25)}

def window_features(window, config, mode):
    y = window.target.to_numpy(dtype=float)
    if len(y) != config['window_size'] or not np.isfinite(y).all():
        raise ValueError('입력 window의 일수 또는 수요 값이 잘못되었습니다.')
    f = {}
    lags = sorted(set(config['lags'] + [config['window_size']]))
    for lag in lags:
        if lag <= len(y):
            f[f'y_lag_{lag}'] = y[-lag]
    for width in sorted(set(config['rolling_windows'] + [config['window_size']])):
        if width <= len(y):
            v = y[-width:]
            for stat, value in [('mean', v.mean()), ('std', v.std()), ('min', v.min()), ('max', v.max())]:
                f[f'y_{stat}_{width}'] = value
    f['recent_trend'] = y[-7:].mean() / max(y[-28:].mean(), 1)
    # Recursive forecasts are available target inputs, not missing-data fills.
    # Keep them out of the imputation feature so later blocks do not receive an
    # out-of-distribution "31 missing days" signal.
    imputed = ~window.target_observed
    if 'target_predicted' in window:
        imputed &= ~window.target_predicted.eq(True)
    f['history_imputed_days'] = int(imputed.sum())
    if mode == 'weather':
        for col in ['temp_avg', 'temp_max', 'temp_min']:
            f[f'{col}_lag_1'] = window[col].iloc[-1]
            for width in [3, 7, 28]:
                f[f'{col}_mean_{width}'] = window[col].iloc[-width:].mean()
    return f

def temperature_response(window, date, weather, config):
    """Use only origin history and supplied weather up to the target day."""
    origin = window.date.iloc[-1]
    history = window.set_index('date')
    temperatures = pd.concat([
        history.temp_avg,
        weather.loc[(weather.index > origin) & (weather.index <= date), 'temp_avg'],
    ]).reindex(pd.date_range(origin - pd.Timedelta(days=27), date))
    avg = temperatures.loc[date]
    hdd = (config['base_temp_hdd'] - temperatures).clip(lower=0)
    f = {'temp_change_1d': avg - temperatures.get(date-pd.Timedelta(days=1), np.nan)}
    for days in [3, 7, 14, 28]:
        values = temperatures.iloc[-days:]
        degree_days = hdd.iloc[-days:]
        # Keep incomplete weather as missing, not as a falsely warm period.
        complete = len(values) == days and values.notna().all()
        f[f'target_temp_mean_{days}'] = values.mean() if complete else np.nan
        f[f'target_temp_min_{days}'] = values.min() if complete else np.nan
        f[f'target_hdd_sum_{days}'] = degree_days.sum() if complete else np.nan
        f[f'target_temp_coverage_{days}'] = float(values.notna().sum()/days)
    f['temp_vs_trailing_7'] = avg - f['target_temp_mean_7']
    for threshold in [0, 5, 10, 15, 18]:
        f[f'cold_degree_below_{threshold}'] = max(threshold-avg, 0) if pd.notna(avg) else np.nan
    f['hdd_squared'] = hdd.iloc[-1] ** 2
    for lag in [364, 365]:
        previous = date - pd.Timedelta(days=lag)
        old_temp = history.temp_avg.get(previous, np.nan)
        old_hdd = max(config['base_temp_hdd']-old_temp, 0) if pd.notna(old_temp) else np.nan
        f[f'annual_temp_delta_{lag}'] = avg-old_temp
        f[f'annual_hdd_delta_{lag}'] = hdd.iloc[-1]-old_hdd
        f[f'annual_temp_{lag}'] = old_temp
    return f

def horizon_features(window, dates, config, mode, weather=None):
    base = window_features(window, config, mode)
    origin = window.date.iloc[-1]
    y = window.set_index('date').target
    rows, references = [], []
    for date in pd.DatetimeIndex(dates):
        h = (date - origin).days
        if not 1 <= h <= config['horizon']:
            raise ValueError('예측일은 origin 이후이며 학습 horizon 이내여야 합니다.')
        f = dict(base, horizon=h, **calendar(date))
        seasonal = []
        for lag in [364, 365]:
            value = y.get(date - pd.Timedelta(days=lag), np.nan)
            f[f'target_date_lag_{lag}'] = value
            if np.isfinite(value):
                seasonal.append(value)
        ref = float(np.mean(seasonal)) if seasonal else float(window.target.iloc[-7:].mean())
        f['seasonal_reference'] = ref
        # Same weekday within the most recent complete week at the origin.
        offset = (origin.dayofweek - date.dayofweek) % 7
        f['recent_same_weekday'] = float(window.target.iloc[-1-offset])
        if config.get('feature_version', 1) >= 2:
            recent_dates = pd.date_range(origin-pd.Timedelta(days=27), origin)
            old = y.reindex(recent_dates-pd.Timedelta(days=364))
            f['annual_recent_level_ratio'] = (
                window.target.iloc[-28:].mean()/max(old.mean(), 1)
                if old.notna().all() else np.nan)
        if mode == 'weather':
            if weather is None:
                raise ValueError('weather 모델에는 예측 기온이 필요합니다.')
            r = weather.loc[date]
            avg, high, low = r['temp_avg'], r['temp_max'], r['temp_min']
            f.update(temp_avg=avg, temp_max=high, temp_min=low, temp_range=high-low,
                     hdd=max(config['base_temp_hdd']-avg, 0) if pd.notna(avg) else np.nan,
                     cdd=max(avg-config['base_temp_cdd'], 0) if pd.notna(avg) else np.nan,
                     temp_change=avg-base['temp_avg_lag_1'])
            if config.get('feature_version', 1) >= 2:
                f.update(temperature_response(window, date, weather, config))
        rows.append(f)
        references.append(ref)
    return pd.DataFrame(rows, dtype=np.float32), np.array(references, dtype=float)
