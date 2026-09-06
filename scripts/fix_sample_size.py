"""Estimate required sample sizes from historical MySQL data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import scipy as sp
from sqlalchemy import text

import data_exchange


ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"


def sample_sizing(history_variance, absolute_mde, alpha=0.05, power=0.8):
    if history_variance <= 0 or absolute_mde <= 0:
        raise ValueError("Historical variance and absolute MDE must be positive.")
    z_alpha = sp.stats.norm.ppf(1 - alpha / 2)
    z_beta = sp.stats.norm.ppf(power)
    return 2 * history_variance * ((z_alpha + z_beta) ** 2) / (absolute_mde**2)


def arpu_sample_sizing(
    engine, history_start, history_end, relative_mde=0.10, alpha=0.05, power=0.8
):
    query = text(
        """
        SELECT *
        FROM vw_MonthlyRevenueStats
        WHERE month_start BETWEEN :first_month AND :last_month
        ORDER BY month_start
        """
    )
    monthly = pd.read_sql(
        query,
        con=engine,
        params={"first_month": history_start, "last_month": history_end},
    )
    if monthly.empty:
        raise RuntimeError("No historical revenue data was found.")

    history_mean = monthly["mean_revenue"].mean()
    history_variance = monthly["var_revenue"].mean()
    absolute_mde = relative_mde * history_mean
    required_per_group = int(
        sample_sizing(history_variance, absolute_mde, alpha, power)
    )
    monthly_users = monthly["num_users"].mean()
    duration_months = (2 * required_per_group) / monthly_users

    print(f"Historical mean ARPU: {history_mean:.2f}")
    print(f"Historical ARPU variance: {history_variance:.2f}")
    print(f"Absolute ARPU MDE: {absolute_mde:.2f}")
    print(f"Required users per group for ARPU: {required_per_group:,}")
    print(f"Estimated duration for ARPU: {duration_months:.2f} months")
    return [
        history_mean,
        history_variance,
        absolute_mde,
        required_per_group,
        duration_months,
    ]


def cr_sample_sizing(
    engine, history_start, history_end, relative_mde=0.05, alpha=0.05, power=0.8
):
    query = text(
        """
        SELECT *
        FROM vw_MonthlyFunnel
        WHERE month_start BETWEEN :first_month AND :last_month
        ORDER BY month_start
        """
    )
    monthly = pd.read_sql(
        query,
        con=engine,
        params={"first_month": history_start, "last_month": history_end},
    )
    if monthly.empty:
        raise RuntimeError("No historical funnel data was found.")

    history_mean = monthly["conversion_rate"].mean()
    history_variance = history_mean * (1 - history_mean)
    absolute_mde = relative_mde * history_mean
    required_per_group = int(
        sample_sizing(history_variance, absolute_mde, alpha, power)
    )
    monthly_users = monthly["num_view"].mean()
    duration_months = (2 * required_per_group) / monthly_users

    print(f"Historical mean conversion rate: {history_mean:.4f}")
    print(f"Historical conversion variance: {history_variance:.4f}")
    print(f"Absolute conversion-rate MDE: {absolute_mde:.4f}")
    print(f"Required users per group for CR: {required_per_group:,}")
    print(f"Estimated duration for CR: {duration_months:.2f} months")
    return [
        history_mean,
        history_variance,
        absolute_mde,
        required_per_group,
        duration_months,
    ]


def main():
    config, engine = data_exchange.connect_to_db()
    history_start = datetime.strptime(
        config["DATA"]["HISTORY_START_DATE"], "%d-%m-%Y"
    ).date()
    history_end = datetime.strptime(
        config["DATA"]["HISTORY_END_DATE"], "%d-%m-%Y"
    ).date()
    first_month = history_start.replace(day=1)
    last_month = history_end.replace(day=1)
    alpha = float(config["EXPERIMENT"]["ALPHA"])
    power = float(config["EXPERIMENT"]["POWER"])

    arpu_stats = arpu_sample_sizing(
        engine,
        first_month,
        last_month,
        float(config["EXPERIMENT"].get("ARPU_MDE", 0.10)),
        alpha,
        power,
    )
    print()
    cr_stats = cr_sample_sizing(
        engine,
        first_month,
        last_month,
        float(config["EXPERIMENT"].get("CR_MDE", 0.05)),
        alpha,
        power,
    )

    metric_stats = pd.DataFrame(
        [arpu_stats, cr_stats],
        columns=["history_mean", "history_var", "mde", "size", "duration_months"],
        index=["ARPU", "CR"],
    )
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = ASSETS_DIR / "metrics_stats.csv"
    metric_stats.to_csv(output_path, float_format="%.4f", index=True)
    print(f"\nSaved sample-size results to {output_path}")


if __name__ == "__main__":
    main()
