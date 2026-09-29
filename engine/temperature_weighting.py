"""Seasonal min/max interpolation calibrated to observed daily averages.

Daylight is astronomical potential sunshine, not measured sunshine duration.
"""
import numpy as np
import pandas as pd


def daylight_hours(dates, latitude):
    """FAO-56 equations 24, 25, 34; latitude in signed decimal degrees."""
    if latitude is None or not np.isfinite(latitude) or not -89.9 <= latitude <= 89.9:
        raise ValueError('기온 관측지 위도(-89.9~89.9°)를 설정하세요. 북위는 양수, 남위는 음수입니다.')
    day = pd.DatetimeIndex(dates).dayofyear.to_numpy(float)
    declination = 0.409*np.sin(2*np.pi*day/365-1.39)
    argument = -np.tan(np.deg2rad(latitude))*np.tan(declination)
    return 24/np.pi*np.arccos(np.clip(argument, -1, 1))


def seasonal_day(dates):
    return pd.to_datetime('2000-'+pd.DatetimeIndex(dates).strftime('%m-%d')).dayofyear.to_numpy()


def fill_weighted_average(weather, history, years, cutoff, latitude, radius=7,
                          prior_days=10.0, min_samples=10):
    result = weather.copy()
    result['temp_avg_source'] = 'provided_average'
    for column in ['temp_avg_weight_max','temp_avg_weight_min','daylight_hours',
                   'weighted_history_samples','historical_mean_weight']:
        result[column] = np.nan
    missing = result.temp_avg.isna()
    if not missing.any():
        return result
    valid_pair = result.temp_min.notna() & result.temp_max.notna() & (result.temp_min <= result.temp_max)
    if (missing & ~valid_pair).any():
        raise ValueError('가중 평균 계산에 유효한 최고·최저 기온 쌍이 필요합니다.')
    equal = missing & result.temp_min.eq(result.temp_max)
    result.loc[equal,'temp_avg'] = result.loc[equal,'temp_min']
    result.loc[equal,'temp_avg_source'] = 'equal_extremes'
    missing &= ~equal
    if not missing.any():
        return result
    required_dates = result.index[missing]
    sunlight = daylight_hours(required_dates, latitude)
    end = pd.Timestamp(cutoff)
    first = pd.Timestamp(year=end.year-years+1, month=1, day=1)
    past = history[history.date.between(first,end)].copy()
    span = past.temp_max-past.temp_min
    ratio = (past.temp_avg-past.temp_min)/span.replace(0,np.nan)
    valid = np.isfinite(ratio) & span.gt(0) & ratio.between(0,1)
    past = past.loc[valid].copy()
    past['ratio'] = ratio.loc[valid]
    if len(past) < min_samples:
        raise ValueError('학습 기온 이력에 평균·최고·최저가 함께 있는 유효 표본이 부족합니다.')
    past['daylight_ratio'] = daylight_hours(past.date, latitude)/24
    historical_day = seasonal_day(past.date)
    target_days = seasonal_day(required_dates)
    for date, target_day, hours in zip(required_dates, target_days, sunlight):
        distance = np.abs(historical_day-target_day)
        distance = np.minimum(distance,366-distance)
        keep = distance <= radius
        if int(keep.sum()) < min_samples:
            raise ValueError(f'{date.date()}: 이전 {years}개년 동일 시기 유효 표본이 {int(keep.sum())}개입니다. 계절 반경/N을 늘리거나 기온 원본을 보완하세요.')
        kernel = 1-distance[keep]/(radius+1)
        selected = past.loc[keep]
        # Learn the historical correction to the daylight prior. Shrink noisy
        # local estimates towards that prior rather than a fixed 50/50 average.
        correction = selected.ratio.to_numpy()-selected.daylight_ratio.to_numpy()
        weight = float(np.clip(hours/24 + np.dot(kernel,correction)/(kernel.sum()+prior_days),0,1))
        result.loc[date,'temp_avg'] = weight*result.loc[date,'temp_max'] + (1-weight)*result.loc[date,'temp_min']
        result.loc[date,'temp_avg_source'] = 'seasonal_daylight_weighted'
        result.loc[date,'temp_avg_weight_max'] = weight
        result.loc[date,'temp_avg_weight_min'] = 1-weight
        result.loc[date,'daylight_hours'] = hours
        result.loc[date,'weighted_history_samples'] = int(keep.sum())
        result.loc[date,'historical_mean_weight'] = float(np.average(selected.ratio,weights=kernel))
    return result
