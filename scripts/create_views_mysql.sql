-- MySQL 8.0+ / MySQL 9.x reporting views.
-- There are no hard-coded experiment dates; filter dates in your report instead.

USE ecommerce_ab_test;

-- Drop dependent views first so this file can be run again safely.
DROP VIEW IF EXISTS vw_ExperimentGroupComparison;
DROP VIEW IF EXISTS vw_ExperimentDailyCumulative;
DROP VIEW IF EXISTS vw_ExperimentDailyFunnel;
-- Remove legacy names from the original Power BI version.
DROP VIEW IF EXISTS vw_PowerBI_GroupComparison;
DROP VIEW IF EXISTS vw_PowerBI_Daily;
DROP VIEW IF EXISTS vw_PowerBI_DailyFunnel;
DROP VIEW IF EXISTS vw_MonthlyRevenueStats;
DROP VIEW IF EXISTS vw_MonthlyFunnel;

CREATE VIEW vw_MonthlyFunnel AS
SELECT
    CAST(DATE_FORMAT(event_timestamp, '%Y-%m-01') AS DATE) AS month_start,
    COUNT(DISTINCT CASE WHEN event_type = 'view' THEN user_id END) AS num_view,
    COUNT(DISTINCT CASE WHEN event_type = 'add_to_basket' THEN user_id END) AS num_add_to_basket,
    COUNT(DISTINCT CASE WHEN event_type = 'checkout' THEN user_id END) AS num_checkout,
    COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN user_id END) AS num_purchase,
    COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN user_id END) * 1.0
        / NULLIF(COUNT(DISTINCT CASE WHEN event_type = 'checkout' THEN user_id END), 0)
        AS conversion_rate
FROM EventLogs
GROUP BY CAST(DATE_FORMAT(event_timestamp, '%Y-%m-01') AS DATE);

CREATE VIEW vw_MonthlyRevenueStats AS
WITH RevenueByMonthUser AS (
    SELECT
        CAST(DATE_FORMAT(event_timestamp, '%Y-%m-01') AS DATE) AS month_start,
        user_id,
        SUM(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS num_view,
        COALESCE(SUM(CASE WHEN event_type = 'purchase' THEN revenue ELSE 0 END), 0)
            AS user_revenue
    FROM EventLogs
    GROUP BY CAST(DATE_FORMAT(event_timestamp, '%Y-%m-01') AS DATE), user_id
)
SELECT
    month_start,
    SUM(CASE WHEN num_view > 0 THEN 1 ELSE 0 END) AS num_users,
    AVG(CASE WHEN num_view > 0 THEN user_revenue END) AS mean_revenue,
    VAR_SAMP(CASE WHEN num_view > 0 THEN user_revenue END) AS var_revenue
FROM RevenueByMonthUser
GROUP BY month_start;

CREATE VIEW vw_ExperimentDailyFunnel AS
WITH DailyFunnelBase AS (
    SELECT
        `date`,
        experiment_id,
        test_group,
        MAX(CASE WHEN event_type = 'view' THEN unique_users END) AS views,
        MAX(CASE WHEN event_type = 'add_to_basket' THEN unique_users END) AS baskets,
        MAX(CASE WHEN event_type = 'checkout' THEN unique_users END) AS checkouts,
        MAX(CASE WHEN event_type = 'purchase' THEN unique_users END) AS purchases,
        COALESCE(MAX(CASE WHEN event_type = 'purchase' THEN total_revenue END), 0) AS revenue
    FROM DailyMetrics
    GROUP BY `date`, experiment_id, test_group
)
SELECT
    `date`,
    experiment_id,
    test_group,
    views,
    baskets,
    checkouts,
    purchases,
    revenue,
    purchases * 1.0 / NULLIF(checkouts, 0) AS conversion_rate,
    revenue * 1.0 / NULLIF(views, 0) AS arpu,
    SUM(COALESCE(purchases, 0)) OVER (
        PARTITION BY experiment_id, test_group ORDER BY `date`
    ) AS cumulative_purchases,
    SUM(COALESCE(checkouts, 0)) OVER (
        PARTITION BY experiment_id, test_group ORDER BY `date`
    ) AS cumulative_checkouts
FROM DailyFunnelBase;

CREATE VIEW vw_ExperimentGroupComparison AS
SELECT
    a.`date`,
    a.experiment_id,
    a.conversion_rate AS group_a_cr,
    b.conversion_rate AS group_b_cr,
    (b.conversion_rate - a.conversion_rate) / NULLIF(a.conversion_rate, 0) * 100
        AS cr_lift_pct,
    a.arpu AS group_a_arpu,
    b.arpu AS group_b_arpu,
    (b.arpu - a.arpu) / NULLIF(a.arpu, 0) * 100 AS arpu_lift_pct
FROM vw_ExperimentDailyFunnel AS a
INNER JOIN vw_ExperimentDailyFunnel AS b
    ON b.`date` = a.`date`
   AND b.experiment_id = a.experiment_id
   AND b.test_group = 'B'
WHERE a.test_group = 'A';

CREATE VIEW vw_ExperimentDailyCumulative AS
SELECT
    dm.`date`,
    dm.experiment_id,
    dm.test_group,
    MAX(CASE WHEN dm.event_type = 'view' THEN mcu.cumulative_unique_users END)
        AS cumulative_unique_views,
    MAX(CASE WHEN dm.event_type = 'checkout' THEN mcu.cumulative_unique_users END)
        AS cumulative_unique_checkouts,
    MAX(CASE WHEN dm.event_type = 'purchase' THEN mcu.cumulative_unique_users END)
        AS cumulative_unique_purchases,
    SUM(COALESCE(MAX(CASE WHEN dm.event_type = 'purchase' THEN dm.total_revenue END), 0))
        OVER (PARTITION BY dm.experiment_id, dm.test_group ORDER BY dm.`date`)
        AS cumulative_revenue
FROM DailyMetrics AS dm
LEFT JOIN MonthlyCumulativeUniqueUsers AS mcu
    ON mcu.`date` = dm.`date`
   AND mcu.experiment_id = dm.experiment_id
   AND mcu.test_group = dm.test_group
   AND mcu.event_type = dm.event_type
GROUP BY dm.`date`, dm.experiment_id, dm.test_group;
