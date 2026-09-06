"""Run the final A/B tests and store their results in MySQL."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import scipy as sp
from sqlalchemy import text

import data_exchange
import db_queries
import local_statistics as local_stat


def save_experiment_result(
    engine,
    experiment_id,
    metric_name,
    control_value,
    variant_value,
    p_value,
    alpha,
    sample_a,
    sample_b,
    duration,
):
    lift = (
        (variant_value - control_value) / control_value
        if control_value != 0
        else None
    )
    delete_statement = text(
        """
        DELETE FROM ExperimentMetrics
        WHERE experiment_id = :experiment_id AND metric_name = :metric_name
        """
    )
    insert_statement = text(
        """
        INSERT INTO ExperimentMetrics (
            experiment_id, metric_name, control_value, variant_value,
            lift, p_value, is_significant, analysis_date,
            sample_size_a, sample_size_b, test_duration_days, notes
        )
        VALUES (
            :experiment_id, :metric_name, :control_value, :variant_value,
            :lift, :p_value, :is_significant, CURRENT_TIMESTAMP,
            :sample_a, :sample_b, :duration, :notes
        )
        """
    )
    values = {
        "experiment_id": experiment_id,
        "metric_name": metric_name,
        "control_value": float(control_value),
        "variant_value": float(variant_value),
        "lift": None if lift is None else float(lift),
        "p_value": float(p_value),
        "is_significant": bool(p_value < alpha),
        "sample_a": int(sample_a),
        "sample_b": int(sample_b),
        "duration": int(duration),
        "notes": f"Two-sided test; alpha={alpha}",
    }
    with engine.begin() as connection:
        connection.execute(delete_statement, values)
        connection.execute(insert_statement, values)
    print(f"Saved {metric_name} result to ExperimentMetrics.")


def require_groups(data, label):
    groups = set(data["test_group"])
    if groups != {"A", "B"}:
        raise RuntimeError(f"{label} must contain groups A and B; found {sorted(groups)}.")


def main():
    config, engine = data_exchange.connect_to_db()
    latest_experiment = pd.read_sql(
        text("SELECT MAX(experiment_id) AS experiment_id FROM Experiments"),
        con=engine,
    ).iloc[0]["experiment_id"]
    if pd.isna(latest_experiment):
        raise RuntimeError("No experiment exists. Run generate_ecomm_data.py first.")
    experiment_id = int(latest_experiment)

    test_start = datetime.strptime(config["DATA"]["TEST_START_DATE"], "%d-%m-%Y")
    test_end = datetime.strptime(config["DATA"]["TEST_END_DATE"], "%d-%m-%Y")
    duration_days = (test_end - test_start).days + 1
    alpha = float(config["EXPERIMENT"]["ALPHA"])
    start_date = test_start.date()
    end_date = test_end.date()

    group_stats = db_queries.get_basic_stats(engine, start_date, end_date)
    require_groups(group_stats, "Experiment statistics")
    group_stats = group_stats.set_index("test_group")

    cr_p_value = local_stat.proportions_z_test(
        group_stats.loc["A", "conversion_rate"],
        group_stats.loc["B", "conversion_rate"],
        group_stats.loc["A", "checkout_count"],
        group_stats.loc["B", "checkout_count"],
    )
    cr_significant = cr_p_value < alpha
    print(
        f"Conversion A={group_stats.loc['A', 'conversion_rate']:.4f}, "
        f"B={group_stats.loc['B', 'conversion_rate']:.4f}, "
        f"p-value={cr_p_value:.6f}, significant={cr_significant}"
    )
    save_experiment_result(
        engine,
        experiment_id,
        "CR",
        group_stats.loc["A", "conversion_rate"],
        group_stats.loc["B", "conversion_rate"],
        cr_p_value,
        alpha,
        group_stats.loc["A", "checkout_count"],
        group_stats.loc["B", "checkout_count"],
        duration_days,
    )

    revenue = db_queries.get_revenue_by_user(engine, start_date, end_date)
    require_groups(revenue, "Experiment revenue")
    group_a_revenue = revenue.loc[revenue["test_group"] == "A", "revenue_sum"]
    group_b_revenue = revenue.loc[revenue["test_group"] == "B", "revenue_sum"]
    _, revenue_p_value = sp.stats.mannwhitneyu(
        group_a_revenue, group_b_revenue, alternative="two-sided"
    )
    revenue_significant = revenue_p_value < alpha
    print(
        f"ARPU A={group_a_revenue.mean():.2f}, "
        f"B={group_b_revenue.mean():.2f}, "
        f"p-value={revenue_p_value:.6f}, significant={revenue_significant}"
    )
    save_experiment_result(
        engine,
        experiment_id,
        "ARPU",
        group_a_revenue.mean(),
        group_b_revenue.mean(),
        revenue_p_value,
        alpha,
        len(group_a_revenue),
        len(group_b_revenue),
        duration_days,
    )


if __name__ == "__main__":
    main()
