# Mac and MySQL Workbench setup

This is the converted MySQL version of the e-commerce A/B-test project. Follow
the steps in order. You do not need Microsoft SQL Server.

## What is already required

- MySQL Community Server
- MySQL Workbench
- Python 3.11 or newer
- This project folder

MySQL Workbench is the visual application. MySQL Community Server is the
database that stores the data. Both are needed. If this works in Terminal, the
server is installed:

    mysql -u root -p

Exit the MySQL prompt with:

    exit;

## Step 1: open the project in Terminal

Replace the path below only if you moved the folder:

    cd "/Users/priyanshudwivedi/Documents/ChatGPT/AB Testing/ecommerce-ab-test-mysql"

Confirm that you are in the correct folder:

    pwd
    ls

You should see README.md, requirements.txt, scripts, assets, and
run_pipeline.py.

## Step 2: create an isolated Python environment

This prevents the project libraries from interfering with other Python
projects on your Mac.

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

When the environment is active, Terminal normally shows (.venv) before the
prompt. In a new Terminal window, reactivate it with:

    cd "/Users/priyanshudwivedi/Documents/ChatGPT/AB Testing/ecommerce-ab-test-mysql"
    source .venv/bin/activate

Leave the environment later with:

    deactivate

## Step 3: create the database tables in Workbench

1. Open MySQL Workbench.
2. Open your local MySQL connection.
3. Choose File > Open SQL Script.
4. Select scripts/create_tables_mysql.sql.
5. Click the lightning-bolt Execute button.
6. Refresh the Schemas panel.
7. Confirm that ecommerce_ab_test appears.

The script creates the database automatically, so it is harmless if you
already created it manually. It uses CREATE TABLE IF NOT EXISTS and will not
delete existing tables.

Verify the tables in a new Workbench query tab:

    USE ecommerce_ab_test;
    SHOW TABLES;

You should see:

- Experiments
- UserAssignments
- EventLogs
- ExperimentMetrics
- DailyMetrics
- MonthlyCumulativeUniqueUsers

## Step 4: create the MySQL procedures

In Workbench:

1. Choose File > Open SQL Script.
2. Select scripts/create_procedures_mysql.sql.
3. Execute the whole file.

These procedures replace the original SQL Server table-valued functions. The
Python application uses equivalent safe queries from scripts/db_queries.py,
while the procedures let you inspect the same calculations in Workbench.

## Step 5: create the reporting views

In Workbench:

1. Open scripts/create_views_mysql.sql.
2. Execute the whole file.

It is normal for the views to be empty at this point because synthetic data
has not been generated yet.

Verify them with:

    USE ecommerce_ab_test;
    SHOW FULL TABLES WHERE Table_type = 'VIEW';

## Step 6: create your private configuration

In Terminal, from the project folder:

    cp scripts/config.example.ini scripts/config.ini

Open it in a simple text editor:

    open -e scripts/config.ini

Change only the database login values initially:

    [DATABASE]
    HOST = 127.0.0.1
    PORT = 3306
    DATABASE = ecommerce_ab_test
    USERNAME = root
    PASSWORD = your_actual_mysql_password

For a first local learning run, using your root account is acceptable. A safer
option is to create a project-only user in Workbench after running the table
script:

    CREATE USER IF NOT EXISTS 'ab_test_user'@'localhost'
        IDENTIFIED BY 'choose_a_new_password';
    GRANT ALL PRIVILEGES ON ecommerce_ab_test.*
        TO 'ab_test_user'@'localhost';

If you do this, put ab_test_user and its new password in config.ini instead of
your root credentials.

Do not upload config.ini to GitHub. It is already covered by .gitignore.

Safer alternative: leave PASSWORD blank and provide it only to your current
Terminal session:

    export ECOMMERCE_DB_PASSWORD='your_actual_mysql_password'

Single quotes protect most special characters. This environment variable
disappears when that Terminal session closes.

## Step 7: test Python-to-MySQL communication

Make sure (.venv) is visible in Terminal, then run:

    python scripts/test_connection.py

Successful output looks like:

    MySQL connection successful.
    Server version: ...
    Selected database: ecommerce_ab_test

Common failures:

### Access denied

The username or password is wrong. First confirm the same credentials work:

    mysql -u root -p

Then correct scripts/config.ini or ECOMMERCE_DB_PASSWORD.

### Can't connect to MySQL server

The MySQL server is stopped or the port is incorrect. Open System Settings >
MySQL and start the server. The usual port is 3306.

### Unknown database

Run scripts/create_tables_mysql.sql in Workbench again.

### No module named pymysql, pandas, or sqlalchemy

Activate the environment and reinstall:

    source .venv/bin/activate
    python -m pip install -r requirements.txt

## Step 8: run the entire Python workflow

The simplest command is:

    python run_pipeline.py

It performs these stages in order:

1. Test the MySQL connection.
2. Delete previously generated demonstration rows.
3. Generate balanced A/B assignments and synthetic events.
4. Calculate sample-size estimates.
5. Validate the historical A/A behavior and the 50:50 split.
6. Aggregate daily experiment metrics and create charts.
7. Run final conversion-rate and ARPU tests.
8. Save final results in ExperimentMetrics.

The data generator intentionally resets the demonstration data on every full
run. It does not drop tables, views, indexes, or constraints.

To run one stage at a time:

    python scripts/generate_ecomm_data.py
    python scripts/fix_sample_size.py
    python scripts/validate_experiment.py
    python scripts/collect_experiment_data.py
    python scripts/analyse_experiment_data.py

## Step 9: inspect results in Workbench

Run:

    USE ecommerce_ab_test;

    SELECT * FROM Experiments;
    SELECT test_group, COUNT(*) AS assigned_users
    FROM UserAssignments
    GROUP BY test_group;

    SELECT * FROM ExperimentMetrics;
    SELECT * FROM vw_ExperimentGroupComparison ORDER BY date;

Try the converted procedures:

    CALL GetBasicStatByGroup('2025-06-01', '2025-06-30');
    CALL GetTotalRevenueByUser('2025-06-01', '2025-06-30');

Generated CSV files and charts are written to the assets folder.

## Files changed for MySQL

- scripts/create_tables_mysql.sql: MySQL schema, AUTO_INCREMENT, checks,
  indexes, defaults, and foreign keys.
- scripts/create_procedures_mysql.sql: MySQL stored-procedure equivalents of
  the SQL Server table-valued functions.
- scripts/create_views_mysql.sql: MySQL date, null, variance, CTE, and window
  function syntax with reusable date ranges.
- scripts/data_exchange.py: SQLAlchemy plus PyMySQL connection.
- scripts/db_queries.py: parameterized equivalents of the former table-valued
  function calls.
- scripts/generate_ecomm_data.py: preserves table definitions and creates a
  deterministic, balanced split.
- scripts/fix_sample_size.py: queries the converted monthly views.
- scripts/validate_experiment.py: MySQL queries and corrected SRM/sample
  denominators.
- scripts/collect_experiment_data.py: MySQL aggregation syntax.
- scripts/analyse_experiment_data.py: MySQL-compatible result storage.

## Streamlit dashboard

After the pipeline completes, start the local dashboard from the project root:

    python -m streamlit run dashboard/app.py

The dashboard reads the platform-neutral reporting view
vw_ExperimentDailyFunnel. Use the Refresh database data button after generating
a fresh experiment.
