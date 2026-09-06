"""Reusable, parameterized MySQL queries used by the analysis scripts.

SQL Server table-valued functions do not have a direct MySQL equivalent.
Keeping these queries here gives the Python pipeline the same results without
building SQL strings with dates supplied by a user.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text


BASIC_STATS_QUERY = text(
    """
    SELECT
        ua.test_group,
        COUNT(DISTINCT CASE WHEN e.event_type = 'view' THEN ua.user_id END) AS view_count,
        COUNT(DISTINCT CASE WHEN e.event_type = 'add_to_basket' THEN ua.user_id END) AS add_to_basket_count,
        COUNT(DISTINCT CASE WHEN e.event_type = 'checkout' THEN ua.user_id END) AS checkout_count,
        COUNT(DISTINCT CASE WHEN e.event_type = 'purchase' THEN ua.user_id END) AS purchase_count,
        COUNT(DISTINCT CASE WHEN e.event_type = 'purchase' THEN ua.user_id END) * 1.0
            / NULLIF(COUNT(DISTINCT CASE WHEN e.event_type = 'checkout' THEN ua.user_id END), 0)
            AS conversion_rate,
        COALESCE(SUM(CASE WHEN e.event_type = 'purchase' THEN e.revenue ELSE 0 END), 0) * 1.0
            / NULLIF(COUNT(DISTINCT CASE WHEN e.event_type = 'view' THEN ua.user_id END), 0)
            AS arpu
    FROM EventLogs AS e
    INNER JOIN UserAssignments AS ua ON ua.user_id = e.user_id
    WHERE e.event_timestamp >= :start_date
      AND e.event_timestamp < DATE_ADD(:end_date, INTERVAL 1 DAY)
    GROUP BY ua.test_group
    ORDER BY ua.test_group
    """
)


REVENUE_BY_USER_QUERY = text(
    """
    SELECT
        ua.test_group,
        ua.user_id,
        COALESCE(SUM(CASE WHEN e.event_type = 'purchase' THEN e.revenue ELSE 0 END), 0)
            AS revenue_sum
    FROM EventLogs AS e
    INNER JOIN UserAssignments AS ua ON ua.user_id = e.user_id
    WHERE e.event_timestamp >= :start_date
      AND e.event_timestamp < DATE_ADD(:end_date, INTERVAL 1 DAY)
    GROUP BY ua.test_group, ua.user_id
    ORDER BY ua.test_group, ua.user_id
    """
)


ASSIGNMENT_COUNTS_QUERY = text(
    """
    SELECT test_group, COUNT(*) AS user_count
    FROM UserAssignments
    WHERE experiment_id = :experiment_id
    GROUP BY test_group
    ORDER BY test_group
    """
)


def get_basic_stats(engine, start_date, end_date):
    return pd.read_sql(
        BASIC_STATS_QUERY,
        con=engine,
        params={"start_date": start_date, "end_date": end_date},
    )


def get_revenue_by_user(engine, start_date, end_date):
    return pd.read_sql(
        REVENUE_BY_USER_QUERY,
        con=engine,
        params={"start_date": start_date, "end_date": end_date},
    )


def get_assignment_counts(engine, experiment_id):
    return pd.read_sql(
        ASSIGNMENT_COUNTS_QUERY,
        con=engine,
        params={"experiment_id": experiment_id},
    )
