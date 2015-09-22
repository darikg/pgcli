import sqlparse
from pgcli.packages.function_metadata import (
    parse_typed_field_list, table_column_names, argument_names)


def test_parse_typed_field_list_simple():
    sql = 'a int, b int[][], c double precision, d text'
    tokens = sqlparse.parse(sql)[0].flatten()
    args = list(parse_typed_field_list(tokens))
    assert [arg.name for arg in args] == ['a', 'b', 'c', 'd']


def test_parse_typed_field_list_more_complex():
    sql = '''   IN a int = 5,
                IN b text default 'abc'::text,
                IN c double precision = 9.99",
                OUT d double precision[]            '''
    tokens = sqlparse.parse(sql)[0].flatten()
    args = list(parse_typed_field_list(tokens))
    assert [arg.name for arg in args] == ['a', 'b', 'c', 'd']
    assert [arg.mode for arg in args] == ['IN', 'IN', 'IN', 'OUT']


def test_parse_typed_field_list_no_arg_names():
    #waiting on sqlparse/169
    sql = 'int, double precision, text'
    tokens = sqlparse.parse(sql)[0].flatten()
    args = list(parse_typed_field_list(tokens))
    assert(len(args) == 3)


def test_table_column_names():
    tbl_str = '''TABLE(
        x INT,
        y DOUBLE PRECISION,
        z TEXT)'''
    names = list(table_column_names(tbl_str))
    assert names == ['x', 'y', 'z']


def test_argument_names():
    func_header = 'IN x INT DEFAULT 2, OUT y DOUBLE PRECISION'
    names = argument_names(func_header, modes=['OUT', 'INOUT'])
    assert list(names) == ['y']


