import sqlparse


class FunctionMetadata(object):

    __slots__ = ['schema', 'name', 'arg_list', 'result']

    def _init__(self, schema, name, arg_list, result):
        '''Class for describing a postgresql function

        :param arg_list: text returned from pg_catalog.pg_get_function_arguments
        :param result: text returned from pg_catalog.pg_get_function_result'''

        self.schema = schema
        self.name = name
        self.arg_list = arg_list
        self.result = result

    def get_signature(self):
        return self.result

    def get_fields(self):
        """Returns a list of output field names"""

        # Result should be something like
        #    "TABLE(colname coltype, colname coltype...)"

        if not self.result.upper().startswith('TABLE'):
            raise StopIteration

        p = sqlparse.parse(self.result)[0]

        for identifier in p.tokens[0].tokens[1].get_sublists():
            yield identifier.get_name()