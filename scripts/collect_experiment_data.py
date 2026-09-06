"""Aggregate MySQL events and create CSV/chart outputs for the experiment."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import text

import data_exchange
import db_queries


ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"


def get_pivoted_df_by_event_type(
    data, event_name, value_col="event_type", agg_func="sum"
):
    filtered = data[data["event_type"] == event_name]
    pivoted = filtered.pivot_table(
        index="date",
        columns="test_group",
        values=value_col,
        aggfunc=agg_func,
        fill_value=0,
    )
    return pivoted.reindex(columns=["A", "B"], fill_value=0)


def plot_bar(data, title, ylabel, filename):
    dates = data.index
    x_values = np.arange(len(dates))
    width = 0.35
    plt.figure(figsize=(10, 5))
    plt.bar(x_values - width / 2, data["A"], width, label="Group A", color="#1F3A5F")
    plt.bar(x_values + width / 2, data["B"], width, label="Group B", color="#C2410C")
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel(ylabel)
    plt.xticks(x_values[::5], [date.strftime("%m-%d") for date in dates[::5]])
    plt.legend()
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_chart(data, title, ylabel, filename):
    dates = data.index
    x_values = np.arange(len(dates))
    plt.figure(figsize=(10, 5))
    plt.plot(x_values, data["A"], label="Group A", color="#1F3A5F")
    plt.plot(x_values, data["B"], label="Group B", color="#C2410C")
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel(ylabel)
    plt.xticks(x_values[::5], [date.strftime("%m-%d") for date in dates[::5]])
    plt.legend()
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def visualize_daily_metrics(engine, start_date, end_date):
    query = text(
        """
        SELECT *
        FROM DailyMetrics
        WHERE `date` BETWEEN :start_date AND :end_date
        ORDER BY `date`, test_group, event_type
        """
    )
    data = pd.read_sql(
        query,
        con=engine,
        params={"start_date": start_date, "end_date": end_date},
    )
    if data.empty:
        raise RuntimeError("No daily metrics were found for the configured test dates.")
    data["date"] = pd.to_datetime(data["date"]).dt.date

    views = get_pivoted_df_by_event_type(data, "view", "event_count")
    baskets = get_pivoted_df_by_event_type(data, "add_to_basket", "event_count")
    checkouts = get_pivoted_df_by_event_type(data, "checkout", "event_count")
    purchases = get_pivoted_df_by_event_type(data, "purchase", "event_count")
    revenue = get_pivoted_df_by_event_type(data, "purchase", "total_revenue")
    unique_checkouts = get_pivoted_df_by_event_type(data, "checkout", "unique_users")
    unique_purchases = get_pivoted_df_by_event_type(data, "purchase", "unique_users")
    conversion = unique_purchases.div(unique_checkouts.replace(0, np.nan)).fillna(0)

    plot_bar(views, "Daily Views", "Count", ASSETS_DIR / "count_views.png")
    plot_bar(baskets, "Daily Add to Basket", "Count", ASSETS_DIR / "count_baskets.png")
    plot_bar(checkouts, "Daily Checkouts", "Count", ASSETS_DIR / "count_checkouts.png")
    plot_bar(purchases, "Daily Purchases", "Count", ASSETS_DIR / "count_purchase.png")
    plot_bar(revenue, "Daily Revenue", "Revenue ($)", ASSETS_DIR / "revenue.png")
    plot_bar(conversion, "Daily Conversion Rate", "Conversion Rate", ASSETS_DIR / "daily_cr.png")
    plot_chart(
        conversion,
        "Daily Conversion Rate",
        "Conversion Rate",
        ASSETS_DIR / "daily_cr_line.png",
    )


def populate_daily_metrics(engine, experiment_id):
    """Build daily and cumulative tables using MySQL syntax."""
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM MonthlyCumulativeUniqueUsers WHERE experiment_id = :id"),
            {"id": experiment_id},
        )
        connection.execute(
            text("DELETE FROM DailyMetrics WHERE experiment_id = :id"),
            {"id": experiment_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO DailyMetrics
                    (`date`, experiment_id, test_group, event_type,
                     event_count, unique_users, total_revenue, created_at)
                SELECT
                    DATE(e.event_timestamp),
                    ua.experiment_id,
                    ua.test_group,
                    e.event_type,
                    COUNT(*) AS event_count,
                    COUNT(DISTINCT e.user_id) AS unique_users,
                    COALESCE(SUM(e.revenue), 0) AS total_revenue,
                    CURRENT_TIMESTAMP
                FROM EventLogs AS e
                INNER JOIN UserAssignments AS ua ON ua.user_id = e.user_id
                WHERE e.event_timestamp IS NOT NULL
                  AND ua.experiment_id = :id
                GROUP BY
                    DATE(e.event_timestamp), ua.experiment_id,
                    ua.test_group, e.event_type
                """
            ),
            {"id": experiment_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO MonthlyCumulativeUniqueUsers
                    (`date`, test_group, experiment_id, event_type,
                     cumulative_unique_users)
                WITH UserFirstSeenInMonth AS (
                    SELECT
                        e.user_id,
                        ua.test_group,
                        ua.experiment_id,
                        e.event_type,
                        EXTRACT(YEAR_MONTH FROM e.event_timestamp) AS event_month,
                        MIN(DATE(e.event_timestamp)) AS first_seen_date
                    FROM EventLogs AS e
                    INNER JOIN UserAssignments AS ua ON ua.user_id = e.user_id
                    WHERE e.event_timestamp IS NOT NULL
                      AND ua.experiment_id = :id
                    GROUP BY
                        e.user_id, ua.test_group, ua.experiment_id,
                        e.event_type, EXTRACT(YEAR_MONTH FROM e.event_timestamp)
                ),
                DailyNewUsers AS (
                    SELECT
                        first_seen_date,
                        test_group,
                        experiment_id,
                        event_type,
                        event_month,
                        COUNT(*) AS new_users
                    FROM UserFirstSeenInMonth
                    GROUP BY
                        first_seen_date, test_group, experiment_id,
                        event_type, event_month
                )
                SELECT
                    daily.first_seen_date,
                    daily.test_group,
                    daily.experiment_id,
                    daily.event_type,
                    SUM(daily.new_users) OVER (
                        PARTITION BY
                            daily.event_month, daily.test_group,
                            daily.experiment_id, daily.event_type
                        ORDER BY daily.first_seen_date
                    )
                FROM DailyNewUsers AS daily
                """
            ),
            {"id": experiment_id},
        )
    print("Daily metrics tables populated successfully.")


def plot_revenue_histogram(engine, start_date, end_date):
    data = db_queries.get_revenue_by_user(engine, start_date, end_date)
    plt.figure(figsize=(10, 5))
    plt.hist(data["revenue_sum"], bins=20, color="#94A3B8")
    plt.title("Experiment Revenue Distribution")
    plt.xlabel("Revenue by user ($)")
    plt.ylabel("Frequency")
    plt.tight_layout()
    plt.savefig(ASSETS_DIR / "experiment_revenue_histogram.png")
    plt.close()


def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    config, engine = data_exchange.connect_to_db()

    experiment_id = pd.read_sql(
        text("SELECT MAX(experiment_id) AS experiment_id FROM Experiments"),
        con=engine,
    ).iloc[0]["experiment_id"]
    if pd.isna(experiment_id):
        raise RuntimeError("No experiment exists. Run generate_ecomm_data.py first.")
    experiment_id = int(experiment_id)
    populate_daily_metrics(engine, experiment_id)

    start_date = datetime.strptime(config["DATA"]["TEST_START_DATE"], "%d-%m-%Y").date()
    end_date = datetime.strptime(config["DATA"]["TEST_END_DATE"], "%d-%m-%Y").date()
    experiment_data = db_queries.get_basic_stats(engine, start_date, end_date)
    output_path = ASSETS_DIR / "experiment_basic_data.csv"
    experiment_data.to_csv(output_path, float_format="%.4f", index=False)

    visualize_daily_metrics(engine, start_date, end_date)
    plot_revenue_histogram(engine, start_date, end_date)
    print(f"Saved experiment data to {output_path}")
    print(f"Saved charts to {ASSETS_DIR}")


if __name__ == "__main__":
    main()
