"""
migrate_to_postgres.py
======================
Script para migrar TODOS los datos de SQLite (psychology.db) a PostgreSQL.

Uso:
    1. Asegúrate de que el contenedor de PostgreSQL está corriendo:
         docker compose up -d
    2. Configura las variables en .env (POSTGRES_USER, POSTGRES_PASSWORD, etc.)
    3. Ejecuta:
         python migrate_to_postgres.py

El script:
  - Lee los datos desde SQLite (psychology.db)
  - Crea las tablas en PostgreSQL si no existen
  - Inserta todos los registros preservando los IDs originales
  - Ajusta las secuencias de PostgreSQL para que los auto-increment
    continúen desde el ID más alto existente.

⚠️  El script NO borra datos previos en PostgreSQL. Si quieres empezar
    limpio, usa:  docker compose down -v  y vuelve a levantar.
"""

import os
import sys
from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine, text
from sqlalchemy import inspect

# Cargar variables de entorno
load_dotenv()

# ── Importar TODOS los modelos para que SQLModel.metadata los conozca ──
from models import (  # noqa: F401
    Psychologist, Patient, Questionnaire, Assignment,
    QuestionnaireCompletion, Session as SessionModel, AssessmentStat,
    Note, Message, AISuggestionLog, AuditLog, PushSubscription, FCMToken,
)

# ── Motores ────────────────────────────────────────────────────────────
sqlite_engine = create_engine("sqlite:///psychology.db", echo=False)

PG_USER = os.getenv("POSTGRES_USER", "psicouja")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "psicouja_secret")
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB   = os.getenv("POSTGRES_DB", "psicouja")
pg_url  = f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
pg_engine = create_engine(pg_url, echo=False)

# ── Orden de migración (respetar dependencias de FK) ──────────────────
TABLE_ORDER = [
    Psychologist,
    Patient,
    Questionnaire,
    Assignment,
    QuestionnaireCompletion,
    SessionModel,
    AssessmentStat,
    Note,
    AISuggestionLog,
    Message,
    AuditLog,
    PushSubscription,
    FCMToken,
]


def get_table_name(model_cls):
    """Obtener el nombre de tabla del modelo."""
    return model_cls.__tablename__


def migrate():
    print("=" * 60)
    print("  MIGRACIÓN  SQLite → PostgreSQL")
    print("=" * 60)

    # 1. Crear tablas en PostgreSQL
    print("\n📦 Creando tablas en PostgreSQL...")
    SQLModel.metadata.create_all(pg_engine)
    print("   ✅ Tablas creadas / verificadas.\n")

    # 2. Migrar cada tabla
    total_rows = 0
    for model_cls in TABLE_ORDER:
        table_name = get_table_name(model_cls)
        print(f"📋 Migrando: {table_name}")

        # Leer desde SQLite
        with Session(sqlite_engine) as sqlite_session:
            rows = sqlite_session.query(model_cls).all()

        if not rows:
            print(f"   ⏭️  (vacía, 0 registros)\n")
            continue

        # Insertar en PostgreSQL
        with Session(pg_engine) as pg_session:
            count = 0
            for row in rows:
                # Crear una copia desvinculada del objeto
                data = {}
                mapper = inspect(model_cls)
                for col in mapper.columns:
                    data[col.key] = getattr(row, col.key)

                new_obj = model_cls(**data)
                pg_session.merge(new_obj)
                count += 1

            pg_session.commit()

        total_rows += count
        print(f"   ✅ {count} registros migrados.\n")

    # 3. Ajustar secuencias de PostgreSQL
    print("🔧 Ajustando secuencias de auto-increment...")
    with Session(pg_engine) as pg_session:
        for model_cls in TABLE_ORDER:
            table_name = get_table_name(model_cls)
            seq_name = f"{table_name}_id_seq"

            # Verificar si la tabla tiene columna 'id'
            try:
                result = pg_session.exec(
                    text(f"SELECT MAX(id) FROM {table_name}")
                )
                max_id = result.one()[0]
                if max_id is not None:
                    pg_session.exec(
                        text(f"SELECT setval('{seq_name}', {max_id})")
                    )
                    print(f"   ✅ {seq_name} → {max_id}")
                else:
                    print(f"   ⏭️  {seq_name} (tabla vacía)")
            except Exception as e:
                print(f"   ⚠️  {seq_name}: {e}")
                pg_session.rollback()

        pg_session.commit()

    print(f"\n{'=' * 60}")
    print(f"  ✅ MIGRACIÓN COMPLETADA: {total_rows} registros totales")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    # Verificar que existe el fichero SQLite
    if not os.path.exists("psychology.db"):
        print("❌ No se encontró psychology.db en el directorio actual.")
        print("   Ejecuta este script desde la carpeta backend/")
        sys.exit(1)

    try:
        migrate()
    except Exception as e:
        print(f"\n❌ Error durante la migración: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
