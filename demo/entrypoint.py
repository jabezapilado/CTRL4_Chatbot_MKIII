"""Start the self-contained CTRL4 demonstration container.

This module is deliberately demo-only.  It waits for the companion MySQL
container, initializes the isolated schema, seeds the fictitious accounts
defined by ``compose.demo.yaml``, then starts the regular Gunicorn process.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import mysql.connector


def wait_for_database() -> None:
    """Wait briefly for the Compose-managed MySQL service to accept TCP."""

    host = os.environ.get("CHATBOT_DB_HOST", "db")
    port = int(os.environ.get("CHATBOT_DB_PORT", "3306"))
    user = os.environ.get("CHATBOT_DB_USER", "ctrl4_demo")
    password = os.environ.get("CHATBOT_DB_PASSWORD", "")
    database = os.environ.get("CHATBOT_DB_NAME", "soc_chatbot_demo")

    for attempt in range(1, 61):
        try:
            connection = mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                connection_timeout=3,
            )
            connection.close()
            return
        except mysql.connector.Error:
            if attempt == 60:
                raise RuntimeError("Demo MySQL did not become ready within five minutes.")
            time.sleep(5)


def main() -> None:
    wait_for_database()
    subprocess.run(
        [sys.executable, "backend/scripts/setup_database.py", "--seed"], check=True
    )
    os.execvp(
        "gunicorn",
        [
            "gunicorn",
            "--workers",
            "1",
            "--chdir",
            "backend",
            "--bind",
            "0.0.0.0:5001",
            "--timeout",
            "180",
            "--access-logfile",
            "-",
            "--error-logfile",
            "-",
            "app:app",
        ],
    )


if __name__ == "__main__":
    main()
