

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






