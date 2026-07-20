import os

import pymysql
import pytest


def connect(user: str, password: str):
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3307")),
        user=user,
        password=password,
        database="shuqi_sandbox",
        charset="utf8mb4",
        autocommit=True,
    )


@pytest.fixture
def reader_connection():
    connection = connect(
        os.environ.get("MYSQL_READER_USER", "sandbox_reader"),
        os.environ["SANDBOX_MYSQL_READER_PASSWORD"],
    )
    yield connection
    connection.close()


@pytest.fixture
def app_connection():
    connection = connect(
        os.environ.get("MYSQL_APP_USER", "sandbox_app"),
        os.environ["SANDBOX_MYSQL_APP_PASSWORD"],
    )
    yield connection
    connection.close()
