import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()
dsn = os.getenv("DATABASE_URL")

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
dsn = os.getenv("DATABASE_URL")

try:
    engine = create_engine(dsn)
    with engine.connect() as conn:
        print("Dropping type 'campaignstatus' if exists...")
        conn.execute(text("DROP TYPE IF EXISTS campaignstatus CASCADE;"))
        conn.commit()
    print("Done.")
except Exception as e:
    print(f"Error: {e}")
