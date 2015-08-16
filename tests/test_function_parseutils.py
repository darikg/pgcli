import pytest
from pgcli.packages.function_parseutils import (
    is_function_def, delineate_function_body)


def test_is_function_def():
    assert is_function_def('CREATE FUNCTION foo()')
    assert is_function_def('CREATE FUNCTION foo()')
    assert not is_function_def('CREATE TABLE foo()')
    assert not is_function_def('SELECT * FROM bar')


def test_delineate_function_simple_language_last():
    sql = "CREATE FUNCTION f1() RETURNS INT AS 'select foo' LANGUAGE SQL"
    start = len("CREATE FUNCTION f1() RETURNS INT AS '")
    stop = len("CREATE FUNCTION f1() RETURNS INT AS 'select foo")
    assert delineate_function_body(sql) == (start, stop)


def test_delineate_function_simple_language_first():
    sql = "CREATE FUNCTION f1() RETURNS INT LANGUAGE SQL AS 'select foo'"
    start = len("CREATE FUNCTION f1() RETURNS INT LANGUAGE SQL AS '")
    stop = len("CREATE FUNCTION f1() RETURNS INT LANGUAGE SQL AS 'select foo")
    assert delineate_function_body(sql) == (start, stop)


def test_delineate_function_simple_language_first_unclosed_quote():
    sql = "CREATE FUNCTION f1() RETURNS INT LANGUAGE SQL AS 'select foo"
    start = len("CREATE FUNCTION f1() RETURNS INT LANGUAGE SQL AS '")
    stop = len("CREATE FUNCTION f1() RETURNS INT LANGUAGE SQL AS 'select foo")
    assert delineate_function_body(sql) == (start, stop)


def test_delineate_function_simple_dollar_quoted_unclosed():
    sql = "CREATE FUNCTION f1() RETURNS INT AS $$select foo"
    start = len("CREATE FUNCTION f1() RETURNS INT AS $$")
    stop = len("CREATE FUNCTION f1() RETURNS INT AS $$select foo")
    assert delineate_function_body(sql) == (start, stop)


def test_delineate_function_simple_dollar_quoted_language_last():
    sql = "CREATE FUNCTION f1() RETURNS INT AS $$select foo$$ LANGUAGE SQL"
    start = len("CREATE FUNCTION f1() RETURNS INT AS $$")
    stop = len("CREATE FUNCTION f1() RETURNS INT AS $$select foo")
    assert delineate_function_body(sql) == (start, stop)


def test_delineate_function_simple_dollar_quoted_language_first():
    sql = "CREATE FUNCTION f1() RETURNS INT LANGUAGE SQL AS $$select foo"
    start = len("CREATE FUNCTION f1() RETURNS INT LANGUAGE SQL AS $$")
    stop = len("CREATE FUNCTION f1() RETURNS INT LANGUAGE SQL AS $$select foo")
    assert delineate_function_body(sql) == (start, stop)


@pytest.mark.parametrize('sql', [
        'CREATE FUNCTION foo() ',
        'CREATE FUNCTION foo (bar ',
        'CREATE FUNCTION foo (bar INT, ',
        'CREATE FUNCTION foo () LANGUAGE SQL ',
    ])
def test_delineate_function_no_body(sql):
    assert delineate_function_body(sql) == (None, None)


def test_delineate_function_with_new_lines():
    sql = '''CREATE FUNCTION f1(a INT, b DOUBLE PRECISION)
             RETURNS TABLE (x INT, y TEXT)
             AS $$'''

    start = stop = len(sql)
    assert delineate_function_body(sql) == (start, stop)