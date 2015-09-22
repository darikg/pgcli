from collections import namedtuple

FunctionMetadata = namedtuple('FunctionMetadata',
                              ['schema_name', 'func_name', 'arg_list', 'result',
                               'is_aggregate', 'is_window', 'is_set_returning'])




