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













