"""Shared MySQL connection helper for the project."""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from sqlalchemy import URL, create_engine


CONFIG_PATH = Path(__file__).with_name("config.ini")

ENVIRONMENT_VARIABLES = {
    "HOST": "ECOMMERCE_DB_HOST",
    "PORT": "ECOMMERCE_DB_PORT",
    "DATABASE": "ECOMMERCE_DB_NAME",
    "USERNAME": "ECOMMERCE_DB_USER",
    "PASSWORD": "ECOMMERCE_DB_PASSWORD",
    "SSL": "ECOMMERCE_DB_SSL",
    "SSL_CA": "ECOMMERCE_DB_SSL_CA",
}


def _database_setting(config, key, default=None):
    """Prefer a cloud environment variable, then the local INI setting."""
    environment_value = os.getenv(ENVIRONMENT_VARIABLES[key])
    if environment_value is not None:
        return environment_value

    if config.has_section("DATABASE"):
        return config["DATABASE"].get(key, default)

    return default


def _as_boolean(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def connect_to_db():
    """Return configuration and an engine for local MySQL or cloud MySQL."""
    config = configparser.ConfigParser()
    local_config_loaded = bool(config.read(CONFIG_PATH))
    cloud_config_available = bool(os.getenv("ECOMMERCE_DB_HOST"))

    if not local_config_loaded and not cloud_config_available:
        raise FileNotFoundError(
            f"Missing {CONFIG_PATH}. Copy scripts/config.example.ini to "
            "scripts/config.ini for local use, or configure the ECOMMERCE_DB_* "
            "environment variables when deploying."
        )

    if local_config_loaded:
        required_sections = {"DATABASE", "EXPERIMENT", "DATA"}
        missing_sections = required_sections.difference(config.sections())
        if missing_sections:
            missing = ", ".join(sorted(missing_sections))
            raise ValueError(f"Missing section(s) in {CONFIG_PATH}: {missing}")

    host = _database_setting(config, "HOST", "127.0.0.1")
    port = int(_database_setting(config, "PORT", 3306))
    database_name = _database_setting(config, "DATABASE", "ecommerce_ab_test")
    username = _database_setting(config, "USERNAME", "root")
    password = _database_setting(config, "PASSWORD", "")
    ssl_enabled = _as_boolean(_database_setting(config, "SSL", "false"))
    ssl_ca = _database_setting(config, "SSL_CA", "")

    connect_args = {}
    if ssl_enabled or ssl_ca:
        connect_args["ssl_verify_cert"] = True
        connect_args["ssl_verify_identity"] = True
        if ssl_ca:
            connect_args["ssl_ca"] = ssl_ca

    connection_url = URL.create(
        drivername="mysql+pymysql",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database_name,
        query={"charset": "utf8mb4"},
    )

    engine = create_engine(
        connection_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    return config, engine
