"""Validate the assignment and historical A/A behavior before analysis."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import scipy as sp
from sqlalchemy import text

import data_exchange
import db_queries
import local_statistics as local_stat


def require_groups(data, label):
    groups = set(data["test_group"])
    if groups != {"A", "B"}:
        raise RuntimeError(f"{label} must contain groups A and B; found {sorted(groups)}.")


def main():
    config, engine = data_exchange.connect_to_db()
    alpha = float(config["EXPERIMENT"]["ALPHA"])
    start_date = datetime.strptime(
        config["DATA"]["HISTORY_START_DATE"], "%d-%m-%Y"
    ).date()
    end_date = datetime.strptime(
        config["DATA"]["HISTORY_END_DATE"], "%d-%m-%Y"
    ).date()

    latest_experiment = pd.read_sql(
        text("SELECT MAX(experiment_id) AS experiment_id FROM Experiments"),
        con=engine,
    ).iloc[0]["experiment_id"]
    if pd.isna(latest_experiment):
        raise RuntimeError("No experiment exists. Run generate_ecomm_data.py first.")
    experiment_id = int(latest_experiment)

    # A/A test: A and B have identical behavior in the generated historical period.
    group_stats = db_queries.get_basic_stats(engine, start_date, end_date)
    require_groups(group_stats, "Historical statistics")
    group_stats = group_stats.set_index("test_group")

    cr_p_value = local_stat.proportions_z_test(
        group_stats.loc["A", "conversion_rate"],
        group_stats.loc["B", "conversion_rate"],
        group_stats.loc["A", "checkout_count"],
        group_stats.loc["B", "checkout_count"],
    )
    if cr_p_value > alpha:
        print(f"A/A conversion check passed (p-value = {cr_p_value:.4f}).")
    else:
        print(
            f"WARNING: A/A conversion check failed (p-value = {cr_p_value:.4f}). "
            "Regenerate or investigate the synthetic data."
        )

    revenue = db_queries.get_revenue_by_user(engine, start_date, end_date)
    require_groups(revenue, "Historical revenue")
    group_a_revenue = revenue.loc[revenue["test_group"] == "A", "revenue_sum"]
    group_b_revenue = revenue.loc[revenue["test_group"] == "B", "revenue_sum"]
    _, revenue_p_value = sp.stats.mannwhitneyu(
        group_a_revenue, group_b_revenue, alternative="two-sided"
    )
    if revenue_p_value > alpha:
        print(f"A/A revenue check passed (p-value = {revenue_p_value:.4f}).")
    else:
        print(
            f"WARNING: A/A revenue check failed (p-value = {revenue_p_value:.4f}). "
            "Regenerate or investigate the synthetic data."
        )

    # SRM must use assigned users, rather than event counts.
    assignments = db_queries.get_assignment_counts(engine, experiment_id)
    require_groups(assignments, "User assignments")
    assignments = assignments.set_index("test_group")
    srm_p_value = local_stat.check_srm(
        assignments.loc["A", "user_count"],
        assignments.loc["B", "user_count"],
    )
    if srm_p_value > 0.01:
        print(f"No sample-ratio mismatch detected (p-value = {srm_p_value:.4f}).")
    else:
        print(
            f"WARNING: Sample-ratio mismatch detected (p-value = {srm_p_value:.4f})."
        )


if __name__ == "__main__":
    main()
