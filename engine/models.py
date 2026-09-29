import numpy as np
import pandas as pd
from .features import horizon_features

class Forecaster:
    def __init__(self, config, mode):
        if mode not in ('weather', 'no_weather'):
            raise ValueError('mode: weather/no_weather')
        self.config, self.mode = config, mode
        self.model = None
        self.meta = {}

    def predict(self, history, dates, weather=None, *, scenario_evaluation=False):
        """Predict one direct block whose dates are within the trained horizon."""
        if self.model is None:
            raise ValueError('학습된 모델을 먼저 불러오세요.')
        w = self.config['window_size']
        if len(history) < w:
            raise ValueError(f'최소 {w}일의 과거 수요가 필요합니다.')
        window = history.iloc[-w:]
        if not pd.DatetimeIndex(window.date).equals(pd.date_range(window.date.iloc[0], window.date.iloc[-1])):
            raise ValueError('입력 window는 연속된 일별 데이터여야 합니다.')
        if not scenario_evaluation and pd.Timestamp(self.meta['trained_through']) > window.date.iloc[-1]:
            raise ValueError('모델 학습 종료일이 예측 origin보다 늦습니다. 해당 과거 시점까지 재학습하세요.')
        x, ref = horizon_features(window, dates, self.config, self.mode, weather)
        if list(x.columns) != self.columns:
            raise ValueError('학습/예측 feature schema가 일치하지 않습니다.')
        values = np.asarray(self.model(x.to_numpy(dtype=np.float32)), dtype=np.float32)
        pred = values.astype(float)
        if self.config['target_transform'] == 'seasonal_log_ratio':
            pred += np.log1p(ref)
        pred = np.maximum(0, np.expm1(pred))
        if not np.isfinite(pred).all():
            raise ValueError('예측값이 유한하지 않습니다.')
        return pred

    def predict_until(self, history, dates, weather=None, *, scenario_evaluation=False):
        """Roll direct blocks forward, moving the window with prior predictions.

        The first block uses observed history. Later blocks append predictions as
        synthetic target history. For weather models, future weather is required
        from the day after the initial origin through the final requested date.
        """
        requested = pd.DatetimeIndex(dates)
        if requested.empty:
            raise ValueError('예측 날짜가 없습니다.')
        if requested.has_duplicates or not requested.is_monotonic_increasing:
            raise ValueError('예측 날짜는 중복 없이 오름차순이어야 합니다.')
        expected = pd.date_range(requested.min(), requested.max(), freq='D')
        if not requested.equals(expected):
            raise ValueError('반복 예측은 연속된 일별 날짜 범위를 사용하세요.')

        expanded = history.copy().sort_values('date').reset_index(drop=True)
        if expanded.empty:
            raise ValueError('과거 수요가 없습니다.')
        initial_origin = pd.Timestamp(expanded.date.iloc[-1])
        if requested.min() <= initial_origin:
            raise ValueError('예측 시작일은 마지막 관측일 다음 날 이후여야 합니다.')

        full_dates = pd.date_range(initial_origin + pd.Timedelta(days=1), requested.max(), freq='D')
        if self.mode == 'weather':
            if weather is None:
                raise ValueError('weather 모델에는 전체 반복 예측 기간의 기온이 필요합니다.')
            weather = weather.reindex(full_dates)
            if weather['temp_avg'].isna().any():
                missing = weather.index[weather['temp_avg'].isna()].strftime('%Y-%m-%d').tolist()
                raise ValueError(f'반복 예측에 필요한 평균기온이 누락되었습니다: {missing[:10]}')

        blocks = []
        cursor = full_dates.min()
        block_number = 1
        while cursor <= full_dates.max():
            block_origin = pd.Timestamp(expanded.date.iloc[-1])
            block_end = min(block_origin + pd.Timedelta(days=self.config['horizon']), full_dates.max())
            if cursor < requested.min():
                block_end = min(block_end, requested.min() - pd.Timedelta(days=1))
            block_dates = pd.date_range(cursor, block_end, freq='D')
            block_weather = weather.loc[block_dates] if self.mode == 'weather' else None
            values = self.predict(expanded, block_dates, block_weather, scenario_evaluation=scenario_evaluation)
            block = pd.DataFrame({
                'date': block_dates,
                'prediction': values,
                'block': block_number,
                'block_origin': block_origin,
                'block_lead': np.arange(1, len(block_dates) + 1),
                'overall_lead': (block_dates - initial_origin).days,
                'uses_predicted_history': block_number > 1,
            })
            blocks.append(block)

            appended = pd.DataFrame({
                'date': block_dates,
                'target': values,
                'target_observed': False,
                'target_predicted': True,
            })
            if self.mode == 'weather':
                for column in ('temp_avg', 'temp_max', 'temp_min'):
                    appended[column] = block_weather[column].to_numpy()
            else:
                for column in ('temp_avg', 'temp_max', 'temp_min'):
                    appended[column] = np.nan
            expanded = pd.concat([expanded, appended], ignore_index=True)
            cursor = block_end + pd.Timedelta(days=1)
            block_number += 1

        result = pd.concat(blocks, ignore_index=True)
        bridge = result[result.date < requested.min()].copy()
        if self.mode == 'weather':
            for col in ('temp_avg', 'temp_max', 'temp_min'):
                bridge[col] = weather.loc[pd.DatetimeIndex(bridge.date), col].to_numpy()
        for col in ('date', 'block_origin'):
            bridge[col] = bridge[col].dt.strftime('%Y-%m-%d')
        requested_result = result[result.date >= requested.min()].reset_index(drop=True)
        requested_result.attrs['bridge_predictions'] = bridge.to_dict('records')
        return requested_result
