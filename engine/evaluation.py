import numpy as np
import pandas as pd

def metrics(actual, predicted):
    y, p = np.asarray(actual, float), np.asarray(predicted, float)
    valid = np.isfinite(y) & np.isfinite(p)
    y, p = y[valid], p[valid]
    if not len(y):
        raise ValueError('평가 가능한 관측 수요가 없습니다.')
    e = p-y
    nz = np.abs(y) > 1e-8
    denominator = np.sum((y-y.mean())**2)
    return {'n': len(y), 'MAE': float(np.abs(e).mean()), 'RMSE': float(np.sqrt(np.mean(e**2))),
            'MAPE': float(np.mean(np.abs(e[nz]/y[nz]))*100) if nz.any() else None,
            'MAPE_excluded_zero_days': int((~nz).sum()),
            'WAPE': float(np.abs(e).sum()/np.abs(y).sum()*100) if np.abs(y).sum() else None,
            'R2': float(1-np.sum(e**2)/denominator) if denominator > 0 else None,
            'bias_pct': float(e.sum()/y.sum()*100) if y.sum() else None}

def summarize_prediction(frame):
    """Summarize forecast output when optional ground truth is attached."""
    if 'actual' not in frame:
        return None, pd.DataFrame()
    data = frame.copy()
    data['date'] = pd.to_datetime(data['date'])
    valid = data[data.actual.notna()]
    if valid.empty:
        return None, pd.DataFrame()
    result = {'prediction': metrics(valid.actual, valid.prediction)}
    monthly = valid.assign(month=valid.date.dt.strftime('%Y-%m')).groupby('month').agg(
        actual=('actual', 'sum'), prediction=('prediction', 'sum'),
        days=('date', 'size')).reset_index()
    monthly['absolute_error'] = (monthly.prediction-monthly.actual).abs()
    monthly['percentage_error'] = monthly.absolute_error / monthly.actual.replace(0,np.nan)*100
    result['monthly_totals'] = metrics(monthly.actual, monthly.prediction) if monthly.actual.notna().any() else None
    return result, monthly
