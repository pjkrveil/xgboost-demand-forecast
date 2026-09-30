# XGBoost Demand Forecast

[Open the demand forecasting test page](https://pjkrveil.github.io/xgboost-demand-forecast/)

A practical demand forecasting test page for daily and monthly demand, weather scenarios, and comparisons with actual demand and business plans.

## XGBoost backbone

- Gradient-boosted decision-tree regression (`gbtree`, squared-error objective).
- The bundled models use 2,000 trees, a maximum depth of 4, and a learning rate of 0.04.
- 116 features combine demand lags, rolling statistics, calendar effects, and weather indicators.
- A 365-day history window feeds a pooled 31-day forecast horizon; longer periods advance recursively in blocks.
- Seasonal log-ratio target transformation and temperature scenarios support weather-sensitive demand analysis.
- Inference runs on the user's computer in a browser Web Worker, using JavaScript for the saved XGBoost trees and Python/WebAssembly for preprocessing. No prediction server or local GPU is required.
