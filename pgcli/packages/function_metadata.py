import sqlparse
from sqlparse.tokens import Whitespace, Comment, Keyword, Name, Punctuation

class FunctionMetadata(object):

    def __init__(self, schema, name, arg_list, result, is_aggregate, is_window,
                 is_set_returning):
        """Class for describing a postgresql function"""

        self.schema_name = schema
        self.func_name = name
        self.arg_list = arg_list
        self.result = result
        self.is_aggregate = is_aggregate
        self.is_window = is_window
        self.is_set_returning = is_set_returning

    def __eq__(self, other):
        return (isinstance(other, self.__class__)
                and self.__dict__ == other.__dict__)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(getattr(self, x) for x in ['schema', 'name', 'arg_list',
                                               'result', 'is_aggregate',
                                               'is_window'])

    def fieldnames(self):
        """Returns a list of output field names"""

        if self.result.lower() == 'void':
            return []
        elif self.result.startswith('TABLE'):
            return list(table_column_names(self.result))
        else:
            return list(argument_names(self.result,
                                              modes=('OUT', 'INOUT')))


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


def table_column_names(sql):
    """Yields column names from a table declaration"""
    #sql is something like "TABLE(x int, y text, ...)"
    sql = sql[6:-1]
    tokens = sqlparse.parse(sql)[0].flatten()
    for field in parse_typed_field_list(tokens):
        if field.name:
            yield field.name


def argument_names(sql, modes=('IN', 'OUT', 'INOUT', 'VARIADIC')):
    """Yields argument names from a function argument list"""
    tokens = sqlparse.parse(sql)[0].flatten()
    for field in parse_typed_field_list(tokens):
        if field and field.mode in modes:
            yield field.name



