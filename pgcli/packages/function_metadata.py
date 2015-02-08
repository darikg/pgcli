import sqlparse
from sqlparse.tokens import Whitespace, Comment, Keyword, Name, Punctuation


class FunctionMetadata(object):

    # __slots__ = ['schema', 'name', 'arg_list', 'result']

    def __init__(self, schema, name, arg_list, result):
        """Class for describing a postgresql function

        :param arg_list: text returned from pg_get_function_arguments
        :param result: text returned from pg_get_function_result"""

        self.schema = schema
        self.name = name
        self._arg_list = arg_list
        self._result = result

        self._fieldnames = None

    @property
    def fieldnames(self):
        """Returns a list of output field names"""

        if self._fieldnames is not None:
            #Already parsed and cached
            return self._fieldnames

        result = self._result
        if self._result.lower() == 'void':
            names = []
        elif self._result.startswith('TABLE'):
            names = list(_table_def_columns(result))
        else:
            names = list(_function_arg_fields(result, modes=('OUT', 'INOUT')))

        self._fieldnames = names
        return names


def _table_def_columns(sql):
    """Yields column names from a table declaration"""
    #sql is something like "TABLE(x int, y text, ...)"
    sql = sql[6:-1]
    tokens = sqlparse.parse(sql)[0].flatten()
    for field in parse_typed_field_list(tokens):
        if field.name:
            yield field.name


def _function_arg_fields(sql, modes=('IN', 'OUT', 'INOUT', 'VARIADIC')):
    """Yields argument names from a function argument list"""
    tokens = sqlparse.parse(sql)[0].flatten()
    for field in parse_typed_field_list(tokens):
        if field and field.mode in modes:
            yield field.name


class TypedFieldMetadata(object):
    """Describes typed field from a function signature or table definition

        Attributes are:
            name        The name of the argument/column
            mode        'IN', 'OUT', 'INOUT', 'VARIADIC'
            type        A list of tokens denoting the type
            default     A list of tokens denoting the default value
            unknown     A list of tokens not assigned to type or default
    """

    __slots__ = ['name', 'mode', 'type', 'default', 'unknown']

    def __init__(self):
        self.name = None
        self.mode = 'IN'
        self.type = []
        self.default = []
        self.unknown = []


def parse_typed_field_list(tokens):
    """Parses a argument/column list, yielding TypedFieldMetadata objects

        Field/column lists are used in function signatures and table
        definitions. This function parses a flattened list of sqlparse tokens
        and yields one metadata argument per argument / column.
    """

    # postgres function argument list syntax:
    #   " ( [ [ argmode ] [ argname ] argtype
    #               [ { DEFAULT | = } default_expr ] [, ...] ] )"

    mode_names = ('IN', 'OUT', 'INOUT', 'VARIADIC')
    parse_state = 'type'
    parens = 0
    field = TypedFieldMetadata()

    for tok in tokens:
        if tok.ttype in Whitespace or tok.ttype in Comment:
            continue
        elif tok.ttype in Punctuation:
            if parens == 0 and tok.value == ',':
                # End of the current field specification
                if field.type:
                    yield field
                field, parse_state = TypedFieldMetadata(), 'type'
            elif parens == 0 and tok.value == '=':
                parse_state = 'default'
            else:
                getattr(field, parse_state).append(tok)
                if tok.value == '(':
                    parens += 1
                elif tok.value == ')':
                    parens -= 1
        elif parens == 0:
            if tok.ttype in Keyword:
                if not field.name and tok.value.upper() in mode_names:
                    # No other keywords allowed before arg name
                    field.mode = tok.value.upper()
                elif tok.value.upper() == 'DEFAULT':
                    parse_state = 'default'
                else:
                    parse_state = 'unknown'
            elif tok.ttype == Name and not field.name:
                # note that `ttype in Name` would also match Name.Builtin
                field.name = tok.value
            else:
                getattr(field, parse_state).append(tok)
        else:
            getattr(field, parse_state).append(tok)

    # Final argument won't be followed by a comma, so make sure it gets yielded
    if field.type:
        yield field



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
