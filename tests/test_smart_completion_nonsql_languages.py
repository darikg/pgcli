import pytest
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document


@pytest.fixture
def completer():
    import pgcli.pgcompleter as pgcompleter
    return pgcompleter.PGCompleter(smart_completion=True)

@pytest.fixture
def complete_event():
    from mock import Mock
    return Mock()


def test_plpython_simple(completer, complete_event):
    pytest.importorskip('jedi')
    sql = 'CREATE FUNCTION mypyfunc() LANGUAGE plpythonu AS $$import '
    pos = len(sql)

    result = set(completer.get_completions(
        Document(text=sql, cursor_position=pos), complete_event))

    assert Completion(text='sys') in result


def test_plpgsql_in_body_simple(completer, complete_event):
    sql = '''CREATE FUNCTION myplpgsql(arg1 INT, arg2 TEXT DEFAULT 'xxxx')
             LANGUAGE plpgsql RETURNS INT AS $$
                DECLARE
                    arg3 DOUBLE PRECISION;
                    arg4 INT[2][2];
                BEGIN

                END $$ '''
    pos = sql.index('BEGIN') + len('BEGIN ')
    results = completer.get_completions(Document(sql, cursor_position=pos),
                                        complete_event)

    args = ['arg1', 'arg2', 'arg3', 'arg4']
    var_completions = set(map(Completion, args))

    # Results should include variable names plus all the standard plpgsql
    # completions
    assert var_completions.issubset(results)
    assert Completion('SELECT') in results


def test_plpgsql_out_body_simple(completer, complete_event):
    sql = 'CREATE OR REPLACE FUNCTION myfunc() VOLAT'
    pos = len(sql)
    results = completer.get_completions(Document(sql, cursor_position=pos),
                                        complete_event)

    assert set(results) == {Completion('VOLATILE', -len('VOLAT'))}

