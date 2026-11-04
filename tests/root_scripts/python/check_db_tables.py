import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not set!")
    exit(1)

engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        print("Connected successfully!")

    inspector = inspect(engine)
    tables = inspector.get_table_names()
except Exception as e:
    print(f"Failed to connect: {e}")
    exit(1)

required_tables = [
    "domain_packs",
    "procedure_metadata",
    "audit_logs",
    "c7_workflows",
    "c7_workflow_executions",
]

print(f"Total tables: {len(tables)}")
for table in required_tables:
    if table in tables:
        print(f"✅ Table found: {table}")
    else:
        print(f"❌ Table missing: {table}")

# Bonus: Check workflow columns for 'version' and check keys
print("\n--- Checking c7_workflows columns ---")
try:
    columns = inspector.get_columns("c7_workflows")
    for col in columns:
        pk = " (PK)" if col["primary_key"] else ""
        print(f"  - {col['name']}: {col['type']}{pk}")
except Exception as e:
    print(f"Error checking c7_workflows: {e}")
