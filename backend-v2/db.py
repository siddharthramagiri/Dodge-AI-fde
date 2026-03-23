import os
from typing import Optional

import psycopg2
from dotenv import load_dotenv


load_dotenv()


DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")


def get_connection():
    """
    Create and return a new psycopg2 connection to Neon PostgreSQL.
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Create a .env file in this directory "
            "with DATABASE_URL=your_neon_url"
        )

    conn = psycopg2.connect(DATABASE_URL)
    # Keep behavior simple for small scripts/queries.
    conn.autocommit = True
    return conn

