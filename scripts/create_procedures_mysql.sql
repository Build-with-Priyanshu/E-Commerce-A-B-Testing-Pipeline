-- MySQL replacement for the original SQL Server table-valued functions.
-- MySQL does not return tables from functions, so these are stored procedures.
-- The Python pipeline uses equivalent parameterized queries in db_queries.py;
-- these procedures are useful for inspecting the same results in Workbench.

USE ecommerce_ab_test;

DROP PROCEDURE IF EXISTS GetBasicStatByGroup;
DROP PROCEDURE IF EXISTS GetTotalRevenueByUser;

DELIMITER $$

CREATE PROCEDURE GetBasicStatByGroup(
    IN p_start_date DATE,
    IN p_end_date DATE
)
BEGIN
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
    WHERE e.event_timestamp >= p_start_date
      AND e.event_timestamp < DATE_ADD(p_end_date, INTERVAL 1 DAY)
    GROUP BY ua.test_group
    ORDER BY ua.test_group;
END$$

CREATE PROCEDURE GetTotalRevenueByUser(
    IN p_start_date DATE,
    IN p_end_date DATE
)
BEGIN
    SELECT
        ua.test_group,
        ua.user_id,
        COALESCE(SUM(CASE WHEN e.event_type = 'purchase' THEN e.revenue ELSE 0 END), 0)
            AS revenue_sum
    FROM EventLogs AS e
    INNER JOIN UserAssignments AS ua ON ua.user_id = e.user_id
    WHERE e.event_timestamp >= p_start_date
      AND e.event_timestamp < DATE_ADD(p_end_date, INTERVAL 1 DAY)
    GROUP BY ua.test_group, ua.user_id
    ORDER BY ua.test_group, ua.user_id;
END$$

DELIMITER ;

-- Workbench examples after data generation:
-- CALL GetBasicStatByGroup('2025-06-01', '2025-06-30');
-- CALL GetTotalRevenueByUser('2025-06-01', '2025-06-30');
