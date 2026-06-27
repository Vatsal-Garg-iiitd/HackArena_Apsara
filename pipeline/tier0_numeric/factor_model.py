"""
Fama-French 5-Factor + Carhart Momentum decomposition.
Downloads factor data from Kenneth French's data library and runs OLS regression
to decompose stock returns into factor exposures and alpha.
"""

import logging
import io
import threading
import zipfile
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests

from pipeline.schemas.tier0 import FactorExposureReport
from pipeline.infra.data_vendor import vendor

logger = logging.getLogger(__name__)

# Cache for factor data (loaded once per session)
_factor_data_cache: Optional[pd.DataFrame] = None
_factor_data_lock = threading.Lock()


def _download_ff_factors() -> Optional[pd.DataFrame]:
    """
    Download Fama-French 5 factors + Momentum from Kenneth French's data library.
    Returns daily factor returns DataFrame with columns: Mkt-RF, SMB, HML, RMW, CMA, Mom, RF
    """
    global _factor_data_cache
    if _factor_data_cache is not None:
        return _factor_data_cache

    with _factor_data_lock:
        if _factor_data_cache is not None:
            return _factor_data_cache

        try:
            # Download 5-factor daily data
            ff5_url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
            response = requests.get(ff5_url, timeout=30)

            if response.status_code != 200:
                logger.warning("Could not download Fama-French 5-factor data")
                return None

            z = zipfile.ZipFile(io.BytesIO(response.content))
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                raw = f.read().decode("utf-8")

            # Parse the CSV — skip header lines
            lines = raw.strip().split("\n")
            header_idx = None
            for i, line in enumerate(lines):
                if "Mkt-RF" in line:
                    header_idx = i
                    break

            if header_idx is None:
                logger.warning("Could not parse Fama-French CSV header")
                return None

            # Find end of data (blank line or non-numeric start)
            data_lines = [lines[header_idx]]
            for line in lines[header_idx + 1:]:
                stripped = line.strip()
                if not stripped or not stripped[0].isdigit():
                    break
                data_lines.append(stripped)

            df = pd.read_csv(io.StringIO("\n".join(data_lines)), skipinitialspace=True)
            df.columns = df.columns.str.strip()

            # First column is date in YYYYMMDD format
            first_col = df.columns[0]
            df.rename(columns={first_col: "Date"}, inplace=True)
            df["Date"] = pd.to_datetime(df["Date"].astype(str), format="%Y%m%d", errors="coerce")
            df.dropna(subset=["Date"], inplace=True)
            df.set_index("Date", inplace=True)

            # Convert from percentage to decimal
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce") / 100.0

            # Try to download momentum factor
            try:
                mom_url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip"
                mom_response = requests.get(mom_url, timeout=30)
                if mom_response.status_code == 200:
                    mz = zipfile.ZipFile(io.BytesIO(mom_response.content))
                    mcsv = mz.namelist()[0]
                    with mz.open(mcsv) as mf:
                        mraw = mf.read().decode("utf-8")

                    mlines = mraw.strip().split("\n")
                    mheader_idx = None
                    for i, line in enumerate(mlines):
                        if "Mom" in line:
                            mheader_idx = i
                            break

                    if mheader_idx is not None:
                        mdata_lines = [mlines[mheader_idx]]
                        for line in mlines[mheader_idx + 1:]:
                            stripped = line.strip()
                            if not stripped or not stripped[0].isdigit():
                                break
                            mdata_lines.append(stripped)

                        mdf = pd.read_csv(io.StringIO("\n".join(mdata_lines)), skipinitialspace=True)
                        mdf.columns = mdf.columns.str.strip()
                        first_col = mdf.columns[0]
                        mdf.rename(columns={first_col: "Date"}, inplace=True)
                        mdf["Date"] = pd.to_datetime(mdf["Date"].astype(str), format="%Y%m%d", errors="coerce")
                        mdf.dropna(subset=["Date"], inplace=True)
                        mdf.set_index("Date", inplace=True)

                        for col in mdf.columns:
                            mdf[col] = pd.to_numeric(mdf[col], errors="coerce") / 100.0

                        if "Mom" in mdf.columns:
                            df["Mom"] = mdf["Mom"]
                        elif len(mdf.columns) > 0:
                            df["Mom"] = mdf.iloc[:, 0]
            except Exception as e:
                logger.warning(f"Could not download momentum factor: {e}")
                df["Mom"] = 0.0

            _factor_data_cache = df
            return df

        except Exception as e:
            logger.error(f"Error downloading Fama-French data: {e}")
            return None


def compute_factor_exposure(
    ticker_symbol: str,
    hist: Optional[pd.DataFrame] = None,
) -> Optional[FactorExposureReport]:
    """
    Run Fama-French 5-factor + Momentum OLS regression on a stock's daily returns.
    Returns factor loadings, alpha, and R-squared.
    """
    # Get 5 years of OHLCV
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")

    if hist is None:
        hist = vendor.get_ohlcv(ticker_symbol, start=start_date, end=end_date)
    if hist is None or len(hist) < 120:
        logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=factor_exposure | reason=insufficient_ohlcv")
        return None

    factors = _download_ff_factors()
    if factors is None:
        logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=factor_exposure | reason=no_factor_data")
        return None

    try:
        # Compute daily returns
        stock_returns = hist["Close"].pct_change().dropna()
        stock_returns.index = stock_returns.index.tz_localize(None)  # Remove timezone for join

        # Align dates
        combined = pd.DataFrame({"stock_ret": stock_returns}).join(factors, how="inner")
        combined.dropna(inplace=True)

        if len(combined) < 60:
            logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=factor_exposure | reason=insufficient_overlap | days={len(combined)}")
            return None

        # Excess return = stock return - risk-free rate
        combined["excess_ret"] = combined["stock_ret"] - combined["RF"]

        # Factor columns
        factor_cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
        if "Mom" in combined.columns:
            factor_cols.append("Mom")

        # Drop rows where any factor is NaN
        combined.dropna(subset=factor_cols + ["excess_ret"], inplace=True)

        if len(combined) < 60:
            return None

        # OLS regression
        from scipy import stats as scipy_stats

        Y = combined["excess_ret"].values
        X = combined[factor_cols].values
        # Add constant for intercept (alpha)
        X_with_const = np.column_stack([np.ones(len(X)), X])

        # Use numpy least squares
        result = np.linalg.lstsq(X_with_const, Y, rcond=None)
        coefficients = result[0]

        alpha_daily = coefficients[0]
        factor_loadings = coefficients[1:]

        # Compute R-squared and t-statistics
        Y_pred = X_with_const @ coefficients
        ss_res = np.sum((Y - Y_pred) ** 2)
        ss_tot = np.sum((Y - Y.mean()) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

        # Standard error of coefficients
        n = len(Y)
        k = len(coefficients)
        if n > k:
            mse = ss_res / (n - k)
            var_covar = mse * np.linalg.inv(X_with_const.T @ X_with_const)
            se = np.sqrt(np.diag(var_covar))
            t_stats = coefficients / se
            alpha_t_stat = float(t_stats[0])
        else:
            alpha_t_stat = 0.0

        # Residual volatility (annualized std of alpha stream)
        residuals = Y - Y_pred
        residual_vol = float(np.std(residuals) * np.sqrt(252))

        # Map factor loadings
        loading_map = {}
        for i, col in enumerate(factor_cols):
            loading_map[col] = float(factor_loadings[i])

        alpha_annualized = float(alpha_daily * 252)

        return FactorExposureReport(
            alpha_annualized=round(alpha_annualized, 6),
            alpha_t_statistic=round(alpha_t_stat, 4),
            alpha_significant=abs(alpha_t_stat) > 2.0,
            market_beta=round(loading_map.get("Mkt-RF", 0.0), 4),
            size_loading=round(loading_map.get("SMB", 0.0), 4),
            value_loading=round(loading_map.get("HML", 0.0), 4),
            profitability_loading=round(loading_map.get("RMW", 0.0), 4),
            investment_loading=round(loading_map.get("CMA", 0.0), 4),
            momentum_loading=round(loading_map.get("Mom", 0.0), 4),
            r_squared=round(float(r_squared), 4),
            residual_volatility=round(residual_vol, 4),
        )

    except Exception as e:
        logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=factor_exposure | reason=regression_error | detail={e}")
        return None
