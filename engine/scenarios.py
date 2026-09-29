"""Calendar climatology, calibrated perturbations and conditional scenarios.

Synthetic 2024/2025 scores are sensitivity diagnostics, never holdout accuracy.
"""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from .preprocessing import TEMP
from .temperature_weighting import fill_weighted_average

DEFAULTS = {
    'climate_years': 5, 'auto_years': True, 'year_candidates': [3, 5, 7, 10],
    'delta_unit': 'sigma', 'delta': 1.645, 'delta_minus': None, 'delta_plus': None, 'auto_delta': True, 'coverage': 0.9,
    'seasonal_radius': 7, 'mc_samples': 30, 'augmentation_samples': 3,
    'scenario_seed': 42, 'representative': 'median',
    'latitude': 37.5665, 'temperature_prior_days': 10.0, 'temperature_min_samples': 10,
}


def settings(config):
    s = dict(DEFAULTS, **config.get('scenario', {}))
    if s['latitude'] is None:
        s['latitude'] = DEFAULTS['latitude']
    return s


def validate_settings(s):
    if not isinstance(s, dict) or set(s) - set(DEFAULTS):
        raise ValueError('scenario 설정 항목을 확인하세요.')
    s = dict(DEFAULTS, **s)
    # Older profiles stored null; use Seoul for those profiles as well.
    if s['latitude'] is None:
        s['latitude'] = DEFAULTS['latitude']
    for key, low, high in [('climate_years', 2, 20), ('seasonal_radius', 1, 30),
                           ('mc_samples', 2, 200), ('augmentation_samples', 1, 20),
                           ('scenario_seed', 0, 2147483647), ('temperature_min_samples', 2, 1000)]:
        v = s[key]
        if isinstance(v, bool) or not isinstance(v, int) or not low <= v <= high:
            raise ValueError(f'{key}: 정수 {low}~{high}')
    for key, low, high in [('delta', 0.1, 5), ('coverage', 0.5, 0.99), ('temperature_prior_days', 0, 1000)]:
        v = s[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) or not low <= v <= high:
            raise ValueError(f'{key}: {low}~{high}')
    if s['delta_unit'] not in ('sigma','celsius'):
        raise ValueError('delta_unit: sigma 또는 celsius')
    delta_limit=20 if s['delta_unit']=='celsius' else 5
    for key in ('delta_minus', 'delta_plus'):

        v = s[key]
        if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) or not 0 <= v <= delta_limit):
            raise ValueError(f"{key}: 0~{delta_limit} ({s['delta_unit']})")
    latitude = s['latitude']
    if latitude is not None and (isinstance(latitude,bool) or not isinstance(latitude,(int,float)) or not np.isfinite(latitude) or not -89.9 <= latitude <= 89.9):
        raise ValueError('latitude: -89.9~89.9 또는 미설정(null)')
    for key in ['auto_years', 'auto_delta']:
        if not isinstance(s[key], bool):
            raise ValueError(f'{key}: true/false')
    if s['representative'] not in ('mean', 'median'):
        raise ValueError('representative: mean/median')
    if not isinstance(s['year_candidates'], list) or not 1 <= len(s['year_candidates']) <= 10:
        raise ValueError('year_candidates: 1~10개 N 후보')
    if any(isinstance(n, bool) or not isinstance(n, int) or not 2 <= n <= 20 for n in s['year_candidates']):
        raise ValueError('N 후보: 정수 2~20')
    return s


def day_index(dates):
    # A leap reference year keeps March dates aligned in every year.
    return pd.to_datetime('2000-' + pd.DatetimeIndex(dates).strftime('%m-%d')).dayofyear.to_numpy() - 1


def climatology(data, dates, years, end_year, radius):
    subset = data[data.date.dt.year.between(end_year-years+1, end_year)].copy()
    for year in range(end_year-years+1, end_year+1):
        part = subset[subset.date.dt.year == year]
        expected = len(pd.date_range(f'{year}-01-01', f'{year}-12-31'))
        if len(part) != expected or part.temp_avg.notna().sum() < 0.9 * expected:
            raise ValueError(f'{year}년 기온 이력이 부족합니다. N을 줄이거나 원본을 보완하세요.')
    index = day_index(subset.date)
    requested = pd.DatetimeIndex(dates)
    result = pd.DataFrame(index=requested)
    for col in ['target'] + TEMP:
        values = subset[col].copy()
        if col == 'target' and 'target_observed' in subset:
            values = values.where(subset.target_observed)
        group = pd.DataFrame({'value': values.to_numpy(), 'day': index})
        group['square'] = group.value ** 2
        agg = group.groupby('day').agg(count=('value', 'count'), total=('value', 'sum'), square=('square', 'sum')).reindex(range(366), fill_value=0)
        a = agg.to_numpy(float)
        pooled = sum(np.roll(a, shift, axis=0) for shift in range(-radius, radius+1))
        count, total, square = pooled.T
        mean = np.divide(total, count, out=np.full(366, np.nan), where=count > 0)
        variance = np.divide(square - total * mean, count-1, out=np.full(366, np.nan), where=count > 1)
        keys = day_index(requested)
        result[col+'_mean'] = mean[keys]
        result[col+'_std'] = np.sqrt(np.maximum(variance[keys], 0))
        result[col+'_count'] = count[keys]
    if result.temp_avg_mean.isna().any() or result.temp_avg_std.isna().any():
        raise ValueError('계절 평균/표준편차 계산에 필요한 기온이 부족합니다.')
    return result


def recommend(data, config):
    """Equal forward-year folds, completed by 2023, independent of scenarios."""
    s = settings(config)
    if not s['auto_years'] and not s['auto_delta']:
        return {'N': s['climate_years'], 'delta': s['delta'], 'coverage': s['coverage'],
                'candidates': [], 'manual': True, 'calibration_end': None}
    history = data[data.date.between(config['train_start'], '2023-12-31')]
    ns = sorted(set(s['year_candidates'] if s['auto_years'] else [s['climate_years']]))
    reference_z = float(norm.ppf((1+s['coverage'])/2))
    scores, errors = [], {}
    # Every N uses exactly the same four calendar-year folds.
    for n in ns:
        losses, zs, folds = [], [], []
        try:
            for year in range(2020, 2024):
                observed = history[history.date.dt.year == year].set_index('date')
                dates = pd.date_range(f'{year}-01-01', f'{year}-12-31')
                if not observed.index.equals(dates):
                    raise ValueError(f'{year}년 의사 결정용 자료가 부족합니다.')
                stats = climatology(history, dates, n, year-1, s['seasonal_radius'])
                fold_losses = []
                for col in ['target'] + TEMP:
                    actual = observed[col].to_numpy(float)
                    if col == 'target':
                        actual = np.where(observed.target_observed, actual, np.nan)
                    mu = stats[col+'_mean'].to_numpy()
                    sigma = stats[col+'_std'].to_numpy()
                    scale = np.nanstd(actual)
                    valid = np.isfinite(actual+mu+sigma) & (sigma > 1e-8)
                    if valid.sum() < len(dates)*0.8:
                        if col in ('target', 'temp_avg'):
                            raise ValueError(f'{year}년 {col}의 통계 표본이 부족합니다.')
                        continue
                    z = np.abs((actual[valid]-mu[valid])/sigma[valid])
                    width = reference_z*sigma[valid]
                    outside = np.maximum(np.abs(actual[valid]-mu[valid])-width, 0)
                    loss = np.mean(2*width+2/(1-s['coverage'])*outside)/max(scale, 1e-8)
                    fold_losses.append(float(loss))
                    zs.extend(z.tolist())
                losses.append(float(np.mean(fold_losses)))
                folds.append({'year': year, 'normalized_interval_score': losses[-1]})
        except ValueError as exc:
            scores.append({'N': n, 'eligible': False, 'reason': str(exc)})
            continue
        errors[n] = zs
        scores.append({'N': n, 'eligible': True, 'score': float(np.mean(losses)), 'folds': folds})
    valid_scores = [r for r in scores if r['eligible']]
    if not valid_scores:
        if s['auto_years'] or s['auto_delta']:
            raise ValueError('N/delta 자동 추천 자료 부족: ' + '; '.join(r['reason'] for r in scores))
        return {'N': s['climate_years'], 'delta': s['delta'], 'coverage': s['coverage'],
                'normal_delta': reference_z, 'candidates': scores, 'calibration_end': '2023-12-31', 'manual': True}
    selected = min(valid_scores, key=lambda r: (r['score'], r['N']))['N']
    empirical = float(np.quantile(errors[selected], s['coverage']))
    delta = float(np.clip(empirical, 0.1, 5)) if s['auto_delta'] else s['delta']
    return {'N': selected, 'delta': delta, 'coverage': s['coverage'],
            'normal_delta': reference_z, 'empirical_delta': empirical,
            'calibration_coverage': float(np.mean(np.asarray(errors[selected]) <= delta)),
            'calibration_end': '2023-12-31', 'candidates': scores,
            'method': 'forward_year_normalized_interval_score_then_absolute_z_quantile'}


def coherent_weather(frame):
    result = frame[TEMP].clip(-60, 60).copy()
    result['temp_min'] = np.minimum(result.temp_min, result.temp_avg)
    result['temp_max'] = np.maximum(result.temp_max, result.temp_avg)
    return result


def shifted_weather(base, stats, z):
    result = base[TEMP].copy()
    for col in TEMP:
        result[col] += np.asarray(z) * stats[col+'_std'].fillna(0).to_numpy()
    return coherent_weather(result)


def persistence(data):
    daily = data.set_index('date').temp_avg
    anomaly = daily-daily.groupby(daily.index.month).transform('mean')
    rho = anomaly.corr(anomaly.shift(1))
    return float(np.clip(rho, 0, 0.95)) if np.isfinite(rho) else 0.0


def latent_path(size, delta, rho, rng):
    """Gaussian AR(1) copula with truncated-normal marginals, not clipped noise."""
    latent = rng.normal(size=size)
    for i in range(1, size):
        latent[i] = rho*latent[i-1] + np.sqrt(1-rho*rho)*latent[i]
    lower, upper = norm.cdf(-delta), norm.cdf(delta)
    return norm.ppf(np.clip(lower+(upper-lower)*norm.cdf(latent), 1e-12, 1-1e-12))


def forecast_scenarios(model, history, dates, provided=None, options=None):
    s = validate_settings(dict(settings(model.config), **(options or {})))
    if model.mode != 'weather':
        raise ValueError('온도 시나리오에는 weather 모델이 필요합니다.')
    if not hasattr(model, 'climate_history'):
        raise ValueError('학습 기온 이력이 없는 이전 모델입니다. 새 코드로 재학습하세요.')
    climate = model.climate_history
    climate_end = pd.Timestamp(model.meta['trained_through'])
    climate = climate[climate.date <= climate_end].copy()
    # Annual climatology uses complete calendar years; a partial latest year
    # remains available for min/max weighting and the demand input window.
    climate_year = climate_end.year if (climate_end.month, climate_end.day) == (12,31) else climate_end.year-1
    config = dict(model.config, scenario=s)
    decision = recommend(climate, config)
    full = pd.date_range(history.date.max()+pd.Timedelta(days=1), pd.Timestamp(dates[-1]))
    stats = climatology(climate, full, decision['N'], climate_year, s['seasonal_radius'])
    fallback_mask=np.ones(len(full),dtype=bool)
    if provided is not None:
        provided = provided.reindex(full).copy()
        bridge_weather = provided[TEMP].isna().all(axis=1)
        fallback_mask=bridge_weather.to_numpy()
        for col in TEMP:
            provided.loc[bridge_weather, col] = stats.loc[bridge_weather, col+'_mean']
        provided = fill_weighted_average(provided.reindex(full), climate, decision['N'], climate_end,
            s['latitude'], s['seasonal_radius'], s['temperature_prior_days'], s['temperature_min_samples'])
        provided.loc[bridge_weather, 'temp_avg_source'] = 'automatic_climatology'
    base = provided.reindex(full)[TEMP] if provided is not None else pd.DataFrame(
        {c: stats[c+'_mean'] for c in TEMP}, index=full)
    base = coherent_weather(base)
    if base.temp_avg.isna().any():
        raise ValueError('전체 예측 기간의 평균기온이 필요합니다.')
    result = model.predict_until(history, dates, base)
    for row in result.attrs.get('bridge_predictions', []):
        date = pd.Timestamp(row['date'])
        row['temperature_source'] = (provided.loc[date, 'temp_avg_source'] if provided is not None
                                     else 'climatology_average')
    central = result.prediction.to_numpy(copy=True)
    paths = []
    # Celsius sensitivity paths are independent of the Monte Carlo Z range.
    default_shift=1.645 if s['delta_unit']=='celsius' else decision['delta']
    minus = s['delta_minus'] if s['delta_minus'] is not None else default_shift
    plus = s['delta_plus'] if s['delta_plus'] is not None else default_shift
    for name, amount in [('minus', -minus), ('plus', plus)]:
        if s['delta_unit']=='celsius':
            weather=base[TEMP]+amount
            if (weather.abs()>60).any().any():
                raise ValueError('온도 변화량 적용 후 기온이 -60~60°C 범위를 벗어납니다. delta를 줄이세요.')
        else:
            weather=shifted_weather(base,stats,amount)
        path = model.predict_until(history, dates, weather).prediction.to_numpy()
        result['prediction_'+name] = path
        for col in TEMP:
            result[col+'_'+name] = weather.loc[dates, col].to_numpy()
        paths.append(path)
    monthly_paths = []
    if fallback_mask.any():
        rho = persistence(climate[climate.date.dt.year > climate_year-decision['N']])
        rng = np.random.default_rng(s['scenario_seed'])
        samples = []
        for i in range(s['mc_samples']):
            weather = shifted_weather(base, stats, latent_path(len(full), decision['delta'], rho, rng))
            weather.loc[~fallback_mask,TEMP]=base.loc[~fallback_mask,TEMP]
            path = model.predict_until(history, dates, weather).prediction.to_numpy()
            samples.append(path)
            monthly_paths.append(pd.Series(path, index=pd.DatetimeIndex(dates)).resample('MS').sum().to_numpy())
        samples = np.asarray(samples)
        alpha = (1-s['coverage'])/2
        result['mc_lower'], result['mc_upper'] = np.quantile(samples, [alpha, 1-alpha], axis=0)
        result['prediction'] = (np.mean(samples, axis=0) if s['representative'] == 'mean' else np.median(samples, axis=0))
        result['mc_std'] = samples.std(axis=0, ddof=1)
        result['mc_mean_standard_error'] = samples.std(axis=0, ddof=1)/np.sqrt(len(samples))
    result['prediction_baseline'] = central
    result['scenario_lower'] = np.minimum.reduce([central, *paths])
    result['scenario_upper'] = np.maximum.reduce([central, *paths])
    for col in TEMP:
        result[col] = base.loc[dates, col].to_numpy()
        result[col+'_std'] = stats.loc[dates, col+'_std'].to_numpy()
        result[col+'_climate_mean'] = stats.loc[dates, col+'_mean'].to_numpy()
        result[col+'_z'] = (result[col]-result[col+'_climate_mean'])/result[col+'_std'].replace(0, np.nan)
    result['temperature_source'] = 'provided' if provided is not None else 'training_climatology_mc'
    if provided is not None:
        origins = provided.get('temp_avg_source', pd.Series('provided_average', index=provided.index))
        result['temp_avg_source'] = origins.reindex(pd.DatetimeIndex(dates)).to_numpy()
        for column in ['temp_avg_weight_max','temp_avg_weight_min','daylight_hours',
                       'weighted_history_samples','historical_mean_weight']:
            result[column] = provided.loc[dates,column].to_numpy()
    else:
        result['temp_avg_source'] = 'climatology_average'
    result['climate_years'] = decision['N']; result['delta_sigma'] = decision['delta']
    result['climatology_fallback']=pd.Series(fallback_mask,index=full).loc[dates].to_numpy()
    result['temperature_source']=np.where(result['climatology_fallback'],'training_climatology_mc','provided')
    result['delta_unit']=s['delta_unit']
    if s['delta_unit']=='celsius':
        result['delta_minus_celsius']=minus;result['delta_plus_celsius']=plus
        for col in TEMP:
            std=result[col+'_std'].replace(0,np.nan)
            result[col+'_delta_minus_z']=-minus/std
            result[col+'_delta_plus_z']=plus/std
        result['delta_minus_sigma']=minus/result['temp_avg_std'].replace(0,np.nan)
        result['delta_plus_sigma']=plus/result['temp_avg_std'].replace(0,np.nan)
    else:
        result['delta_minus_sigma']=minus;result['delta_plus_sigma']=plus
    monthly = result.assign(month=result.date.dt.strftime('%Y-%m')).groupby('month')[[
        'prediction', 'prediction_baseline', 'prediction_minus', 'prediction_plus']].sum().reset_index()
    monthly['scenario_lower'] = monthly[['prediction_baseline','prediction_minus','prediction_plus']].min(axis=1)
    monthly['scenario_upper'] = monthly[['prediction_baseline','prediction_minus','prediction_plus']].max(axis=1)
    if monthly_paths:
        alpha = (1-s['coverage'])/2
        monthly['mc_lower'], monthly['mc_upper'] = np.quantile(monthly_paths, [alpha,1-alpha], axis=0)
    result.attrs['scenario_metadata'] = dict(decision, settings=s,
        average_temperature_method='seasonal_daylight_shrinkage_v1',
        average_temperature_sources={str(k):int(v) for k,v in result.temp_avg_source.value_counts().items()},
        interval_kind='conditional_temperature_sensitivity_not_total_forecast_uncertainty',
        climate_through=str(climate_end.date()), climatology_end_year=climate_year,
        fallback_days=int(fallback_mask.sum()),mc_runs=s['mc_samples'] if fallback_mask.any() else 0)
    result.attrs['scenario_monthly'] = monthly.to_dict('records')
    return result
