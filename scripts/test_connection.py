"""Small connection check to run before the data pipeline."""

from sqlalchemy import text

import data_exchange


def main():
    _, engine = data_exchange.connect_to_db()
    with engine.connect() as connection:
        version = connection.execute(text("SELECT VERSION()")).scalar_one()
        database = connection.execute(text("SELECT DATABASE()")).scalar_one()
    print("MySQL connection successful.")
    print(f"Server version: {version}")
    print(f"Selected database: {database}")


if __name__ == "__main__":
    main()
