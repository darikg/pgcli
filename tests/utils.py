import pytest
import psycopg2
import psycopg2.extras
from pgcli.main import format_output
from pgcli.pgexecute import register_json_typecasters

# TODO: should this be somehow be divined from environment?
POSTGRES_USER, POSTGRES_HOST = 'postgres', 'localhost'


def db_connection(dbname=None):
    conn = psycopg2.connect(user=POSTGRES_USER, host=POSTGRES_HOST, database=dbname)
    conn.autocommit = True
    return conn


CAN_CONNECT_TO_DB = JSON_AVAILABLE = JSONB_AVAILABLE = False
SERVER_VERSION = 0


dbtest = pytest.mark.skipif(
    not CAN_CONNECT_TO_DB,
    reason="Need a postgres instance at localhost accessible by user 'postgres'")


requires_json = pytest.mark.skipif(
    not JSON_AVAILABLE,
    reason='Postgres server unavailable or json type not defined')


requires_jsonb = pytest.mark.skipif(
    not JSONB_AVAILABLE,
    reason='Postgres server unavailable or jsonb type not defined')


def create_db(dbname):
    with db_connection().cursor() as cur:
        try:
            cur.execute('''CREATE DATABASE _test_db''')
        except:
            pass


def drop_tables(conn):
    with conn.cursor() as cur:
        cur.execute('''
            DROP SCHEMA public CASCADE;
            CREATE SCHEMA public;
            DROP SCHEMA IF EXISTS schema1 CASCADE;
            DROP SCHEMA IF EXISTS schema2 CASCADE''')


def run(executor, sql, join=False, expanded=False, pgspecial=None):
    " Return string output for the sql to be run "
    result = []
    for title, rows, headers, status in executor.run(sql, pgspecial):
        result.extend(format_output(title, rows, headers, status, 'psql',
                                    expanded=expanded))
    if join:
        result = '\n'.join(result)
    return result
