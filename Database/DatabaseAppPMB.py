# DatabaseAppPMB.py for V6
import os
import psycopg2
import psycopg2.extras
from flask import g

# connection string
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:YourVeryStrongPassword@db:5432/v3db")



def get_db():
    """Returns a psycopg2 connection, stored in Flask's `g`."""
    if 'db' not in g:
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        g.db = conn
    return g.db

def close_db(exc=None):
    """Closes the connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Creates tables and seeds the patients if needed."""
    schema = """
    CREATE TABLE IF NOT EXISTS patients (
      id   SERIAL PRIMARY KEY,
      name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS vitals (
      id         SERIAL PRIMARY KEY,
      patient_id INTEGER REFERENCES patients(id),
      timestamp  TIMESTAMP WITHOUT TIME ZONE
                 DEFAULT (NOW() AT TIME ZONE 'utc'),
      pulse      INTEGER NOT NULL,
      bp         TEXT    NOT NULL,
      spo2       INTEGER NOT NULL
    );
    """
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute(schema)
            # seed 5 patients
            for i in range(1,6):
                cur.execute(
                    "INSERT INTO patients(name) VALUES (%s) "
                    "ON CONFLICT (name) DO NOTHING;",
                    (f"patient_{i}",)
                )
