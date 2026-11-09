"""Pool de conexiones a PostgreSQL.

Database per Service: cada servicio se conecta con su propio usuario y solo
tiene permisos sobre su esquema (ver postgres/init.sql).
"""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def crear_pool(dsn: str, esquema: str, max_size: int = 10) -> ConnectionPool:
    return ConnectionPool(
        dsn,
        min_size=1,
        max_size=max_size,
        kwargs={"options": f"-c search_path={esquema}", "row_factory": dict_row},
        open=True,
        timeout=5,
    )
