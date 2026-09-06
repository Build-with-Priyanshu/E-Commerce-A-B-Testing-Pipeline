"""Generate reproducible synthetic history and A/B-test data in MySQL."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker
from sqlalchemy import text

import data_exchange


RANDOM_SEED = 42
fake = Faker()


def generate_experiment_description(test_name: str, null_hypothesis: str) -> dict:
    return {
        "experiment_name": test_name,
        "hypothesis": null_hypothesis,
        "status": "running",
    }


def generate_users(num_users: int, experiment_id: int) -> pd.DataFrame:
    """Generate a randomized, nearly exact 50:50 A/B assignment."""
    user_ids = [str(fake.unique.uuid4()) for _ in range(num_users)]
    groups = np.array(["A"] * (num_users // 2) + ["B"] * (num_users - num_users // 2))
    np.random.shuffle(groups)

    return pd.DataFrame(
        {
            "user_id": user_ids,
            "experiment_id": experiment_id,
            "test_group": groups,
            "assigned_at": datetime.now(),
        }
    )


def generate_session(uid, group, start_date, end_date, is_test_period=False):
    """Generate one view-to-purchase funnel session for a user."""
    events = []
    timestamp = fake.date_time_between(start_date=start_date, end_date=end_date)
    device = np.random.choice(["mobile", "desktop", "tablet"], p=[0.6, 0.3, 0.1])

    conversion_probability = 0.60
    revenue_multiplier = 1.0
    if is_test_period and group == "B":
        conversion_probability = 0.63
        revenue_multiplier = 1.04

    events.append([uid, "view", timestamp, device, None])

    if random.random() < 0.4:
        events.append([uid, "add_to_basket", timestamp + timedelta(minutes=2), device, None])
        if random.random() < 0.5:
            events.append([uid, "checkout", timestamp + timedelta(minutes=5), device, None])
            if random.random() < conversion_probability:
                revenue = np.random.lognormal(3.5, 0.8) * revenue_multiplier
                events.append(
                    [uid, "purchase", timestamp + timedelta(minutes=7), device, round(revenue, 2)]
                )

    return events


def generate_events(
    users: pd.DataFrame,
    history_start: datetime,
    history_end: datetime,
    test_start: datetime,
    test_end: datetime,
) -> pd.DataFrame:
    if history_start > history_end or test_start > test_end:
        raise ValueError("A start date cannot be later than its end date.")
    if history_end >= test_start:
        raise ValueError("The history period must end before the test period starts.")

    events = []
    history_sessions = max(1, round(((history_end - history_start).days + 1) / 10))
    test_sessions = max(1, round(((test_end - test_start).days + 1) / 10))

    for row in users.itertuples(index=False):
        for _ in range(history_sessions):
            events.extend(
                generate_session(
                    row.user_id, row.test_group, history_start, history_end, False
                )
            )
        for _ in range(test_sessions):
            events.extend(
                generate_session(row.user_id, row.test_group, test_start, test_end, True)
            )

    return pd.DataFrame(
        events,
        columns=["user_id", "event_type", "event_timestamp", "device", "revenue"],
    )


def clear_demo_data(engine):
    """Clear old generated results while preserving the MySQL table definitions."""
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM ExperimentMetrics"))
        connection.execute(text("DELETE FROM MonthlyCumulativeUniqueUsers"))
        connection.execute(text("DELETE FROM DailyMetrics"))
        connection.execute(text("DELETE FROM EventLogs"))
        connection.execute(text("DELETE FROM UserAssignments"))
        connection.execute(text("DELETE FROM Experiments"))


def main():
    Faker.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    random.seed(RANDOM_SEED)

    config, engine = data_exchange.connect_to_db()
    clear_demo_data(engine)

    experiment = generate_experiment_description(
        config["EXPERIMENT"]["NAME"], config["EXPERIMENT"]["H0"]
    )
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                INSERT INTO Experiments (experiment_name, hypothesis, status)
                VALUES (:experiment_name, :hypothesis, :status)
                """
            ),
            experiment,
        )
        experiment_id = result.lastrowid

    users = generate_users(int(config["DATA"]["NUM_USERS"]), experiment_id)
    group_counts = users["test_group"].value_counts().sort_index()
    print(f"Users assigned to A: {group_counts.get('A', 0)}")
    print(f"Users assigned to B: {group_counts.get('B', 0)}")

    history_start = datetime.strptime(config["DATA"]["HISTORY_START_DATE"], "%d-%m-%Y")
    history_end = datetime.strptime(config["DATA"]["HISTORY_END_DATE"], "%d-%m-%Y")
    test_start = datetime.strptime(config["DATA"]["TEST_START_DATE"], "%d-%m-%Y")
    test_end = datetime.strptime(config["DATA"]["TEST_END_DATE"], "%d-%m-%Y")
    events = generate_events(users, history_start, history_end, test_start, test_end)

    # Append keeps the keys, indexes, checks, and foreign keys from create_tables_mysql.sql.
    users.to_sql(
        "UserAssignments",
        con=engine,
        if_exists="append",
        index=False,
        chunksize=1000,
    )
    events.to_sql(
        "EventLogs",
        con=engine,
        if_exists="append",
        index=False,
        chunksize=1000,
    )
    print(f"Uploaded {len(users):,} users and {len(events):,} events successfully.")


if __name__ == "__main__":
    main()
