import pandas as pd
import streamlit as st
from sqlalchemy import text

from scripts import data_exchange, db_queries


st.set_page_config(
    page_title="E-commerce A/B Test",
    page_icon="📊",
    layout="wide",
)


@st.cache_resource
def get_database_engine():
    """Create and reuse the MySQL connection engine."""
    _, engine = data_exchange.connect_to_db()
    return engine


@st.cache_data(ttl=60)
def load_experiments():
    query = text("""
        SELECT
            experiment_id,
            experiment_name,
            hypothesis,
            status
        FROM Experiments
        ORDER BY experiment_id DESC
    """)

    return pd.read_sql(query, con=get_database_engine())


@st.cache_data(ttl=60)
def load_final_metrics(experiment_id):
    query = text("""
        SELECT
            metric_name,
            control_value,
            variant_value,
            lift,
            p_value,
            is_significant,
            sample_size_a,
            sample_size_b,
            test_duration_days
        FROM ExperimentMetrics
        WHERE experiment_id = :experiment_id
        ORDER BY metric_name
    """)

    return pd.read_sql(
        query,
        con=get_database_engine(),
        params={"experiment_id": experiment_id},
    )


@st.cache_data(ttl=60)
def load_daily_metrics(experiment_id):
    query = text("""
        SELECT
            date,
            test_group,
            views,
            baskets,
            checkouts,
            purchases,
            revenue,
            conversion_rate,
            arpu,
            cumulative_purchases,
            cumulative_checkouts
        FROM vw_ExperimentDailyFunnel
        WHERE experiment_id = :experiment_id
        ORDER BY `date`, test_group
    """)

    data = pd.read_sql(
        query,
        con=get_database_engine(),
        params={"experiment_id": experiment_id},
    )

    data["date"] = pd.to_datetime(data["date"])
    return data


@st.cache_data(ttl=60)
def load_assignment_counts(experiment_id):
    query = text("""
        SELECT
            test_group,
            COUNT(*) AS assigned_users
        FROM UserAssignments
        WHERE experiment_id = :experiment_id
        GROUP BY test_group
        ORDER BY test_group
    """)

    return pd.read_sql(
        query,
        con=get_database_engine(),
        params={"experiment_id": experiment_id},
    )


@st.cache_data(ttl=60)
def load_basic_statistics(start_date, end_date):
    return db_queries.get_basic_stats(
        get_database_engine(),
        start_date,
        end_date,
    )


def get_metric(metrics, metric_name):
    selected = metrics[metrics["metric_name"] == metric_name]

    if selected.empty:
        return None

    return selected.iloc[0]


def show_final_results(metrics):
    conversion = get_metric(metrics, "CR")
    arpu = get_metric(metrics, "ARPU")

    if conversion is None or arpu is None:
        st.warning(
            "Final metrics are unavailable. "
            "Run analyse_experiment_data.py first."
        )
        return

    st.subheader("Final experiment results")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Control conversion",
        f"{conversion['control_value']:.2%}",
    )

    col2.metric(
        "Variant conversion",
        f"{conversion['variant_value']:.2%}",
        delta=f"{conversion['lift']:.2%}",
    )

    col3.metric(
        "Conversion p-value",
        f"{conversion['p_value']:.6f}",
    )

    col4, col5, col6 = st.columns(3)

    col4.metric(
        "Control ARPU",
        f"${arpu['control_value']:.2f}",
    )

    col5.metric(
        "Variant ARPU",
        f"${arpu['variant_value']:.2f}",
        delta=f"{arpu['lift']:.2%}",
    )

    col6.metric(
        "ARPU p-value",
        f"{arpu['p_value']:.6f}",
    )

    cr_significant = bool(conversion["is_significant"])
    arpu_significant = bool(arpu["is_significant"])

    if cr_significant and arpu_significant:
        st.success(
            "Both conversion rate and ARPU show statistically "
            "significant differences."
        )
    else:
        st.warning(
            "At least one metric is not statistically significant."
        )


def show_daily_charts(daily_data):
    st.subheader("Daily performance")

    conversion_chart = daily_data.pivot(
        index="date",
        columns="test_group",
        values="conversion_rate",
    )

    revenue_chart = daily_data.pivot(
        index="date",
        columns="test_group",
        values="revenue",
    )

    purchase_chart = daily_data.pivot(
        index="date",
        columns="test_group",
        values="cumulative_purchases",
    )

    left, right = st.columns(2)

    with left:
        st.write("Daily conversion rate")
        st.line_chart(conversion_chart)

    with right:
        st.write("Daily revenue")
        st.line_chart(revenue_chart)

    st.write("Cumulative purchases")
    st.line_chart(purchase_chart)


def show_funnel(basic_statistics):
    st.subheader("Experiment funnel")

    funnel = basic_statistics.set_index("test_group")[
        [
            "view_count",
            "add_to_basket_count",
            "checkout_count",
            "purchase_count",
        ]
    ].transpose()

    funnel.index = [
        "Views",
        "Added to basket",
        "Checkouts",
        "Purchases",
    ]

    st.bar_chart(funnel)

    with st.expander("View funnel data"):
        st.dataframe(
            basic_statistics,
            width="stretch",
            hide_index=True,
        )


def main():
    st.title("E-commerce A/B Test")
    st.caption(
        "Apple Pay and Google Pay checkout experiment"
    )

    try:
        experiments = load_experiments()
    except Exception as error:
        st.error("The dashboard could not connect to MySQL.")
        st.exception(error)
        st.stop()

    if experiments.empty:
        st.warning(
            "No experiments were found. Run the Python pipeline first."
        )
        st.stop()

    experiment_options = experiments.set_index(
        "experiment_id"
    )["experiment_name"].to_dict()

    experiment_id = st.sidebar.selectbox(
        "Select experiment",
        options=list(experiment_options.keys()),
        format_func=lambda value: experiment_options[value],
    )

    if st.sidebar.button("Refresh database data"):
        st.cache_data.clear()
        st.rerun()

    selected_experiment = experiments[
        experiments["experiment_id"] == experiment_id
    ].iloc[0]

    st.write(f"**Hypothesis:** {selected_experiment['hypothesis']}")
    st.write(f"**Status:** {selected_experiment['status']}")

    metrics = load_final_metrics(experiment_id)
    daily_data = load_daily_metrics(experiment_id)
    assignments = load_assignment_counts(experiment_id)

    if daily_data.empty:
        st.warning(
            "No daily metrics exist. Run collect_experiment_data.py."
        )
        st.stop()

    st.subheader("User assignment")

    assignment_columns = st.columns(len(assignments))

    for column, row in zip(
        assignment_columns,
        assignments.itertuples(index=False),
    ):
        column.metric(
            f"Group {row.test_group}",
            f"{row.assigned_users:,}",
        )

    show_final_results(metrics)

    minimum_date = daily_data["date"].min().date()
    maximum_date = daily_data["date"].max().date()

    selected_dates = st.sidebar.date_input(
        "Daily chart period",
        value=(minimum_date, maximum_date),
        min_value=minimum_date,
        max_value=maximum_date,
    )

    if len(selected_dates) != 2:
        st.info("Select both a start date and an end date.")
        st.stop()

    start_date, end_date = selected_dates

    filtered_daily = daily_data[
        (daily_data["date"].dt.date >= start_date)
        & (daily_data["date"].dt.date <= end_date)
    ]

    basic_statistics = load_basic_statistics(
        start_date,
        end_date,
    )

    show_daily_charts(filtered_daily)
    show_funnel(basic_statistics)

    with st.expander("View daily database data"):
        st.dataframe(
            filtered_daily,
            width="stretch",
            hide_index=True,
        )


if __name__ == "__main__":
    main()
