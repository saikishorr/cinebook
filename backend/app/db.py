from collections.abc import Iterator
from fastapi import Request
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

def create_pool(database_url: str) -> ConnectionPool:
    # dict_row returns SQL rows as dictionaries keyed by column name.
    return ConnectionPool(database_url, kwargs={"row_factory": dict_row}, open=False)

def get_connection(request: Request) -> Iterator:
    # The pool returns this connection after the request completes.
    with request.app.state.pool.connection() as connection:
        yield connection
