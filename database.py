import os
from sqlmodel import SQLModel, create_engine, Session
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Selección de base de datos mediante variable de entorno DB_TYPE
#   - "sqlite"     → usa psychology.db local  (por defecto)
#   - "postgresql"  → usa PostgreSQL (ver POSTGRES_* en .env)
# ---------------------------------------------------------------------------

DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

if DB_TYPE == "postgresql":
    PG_USER = os.getenv("POSTGRES_USER", "psicouja")
    PG_PASS = os.getenv("POSTGRES_PASSWORD", "psicouja_secret")
    PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
    PG_PORT = os.getenv("POSTGRES_PORT", "5432")
    PG_DB   = os.getenv("POSTGRES_DB", "psicouja")

    DATABASE_URL = (
        f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    )
    engine = create_engine(DATABASE_URL, echo=False)
else:
    sqlite_file_name = "psychology.db"
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    engine = create_engine(sqlite_url, echo=False)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
