class Suggestion(object):

    __slots__ = ()

    def _to_tuple(self):
        return tuple(self.__getattribute__(s) for s in self.__slots__)

    def __eq__(self, other):
        return self._to_tuple() == other

    def __hash__(self):
        return hash(self._to_tuple())

    def __repr__(self):
        fields = ', '.join('{}={}'.format(s, self.__getattribute__(s))
                           for s in self.__slots__)
        return self.__class__.__name__ + '(' + fields + ')'


class Special(Suggestion):
    __slots__ = ()


class Database(Suggestion):
    __slots__ = ()


class Schema(Suggestion):
    __slots__ = ()


class FromClauseItem(Suggestion):
    """FromClauseItem is a table/view/function used in the FROM clause
    `table_refs` contains the list of tables/... already in the statement,
     used to ensure that the alias we suggest is unique
     """

    __slots__ = ('schema', 'table_refs', 'local_tables')

    def __init__(self, schema=None, table_refs=tuple(), local_tables=tuple()):
        self.schema = schema
        self.table_refs = table_refs
        self.local_tables = local_tables


class Table(Suggestion):

    __slots__ = ('schema', 'table_refs', 'local_tables')

    def __init__(self, schema=None, table_refs=tuple(), local_tables=tuple()):
        self.schema = schema
        self.table_refs = table_refs
        self.local_tables = local_tables


class View(Suggestion):

    __slots__ = ('schema', 'table_refs', 'local_tables')

    def __init__(self, schema=None, table_refs=tuple(), local_tables=tuple()):
        self.schema = schema
        self.table_refs = table_refs
        self.local_tables = local_tables


class JoinCondition(Suggestion):
    """JoinConditions are suggested after ON, e.g. 'foo.barid = bar.barid'"""

    __slots__ = ('table_refs', 'parent')

    def __init__(self, table_refs, parent):
        self.table_refs = table_refs
        self.parent = parent


class Join(Suggestion):
    """Joins are suggested after JOIN, e.g. 'foo ON foo.barid = bar.barid'"""

    __slots__ = ('table_refs', 'schema')

    def __init__(self, table_refs, schema):
        self.table_refs = table_refs
        self.schema = schema


class Function(Suggestion):

    __slots__ = ('schema', 'table_refs', 'filter')

    def __init__(self, schema=None, table_refs=tuple(), filter=None):
        self.schema = schema
        self.table_refs = table_refs
        self.filter = filter


class Column(Suggestion):

    __slots__ = ('table_refs', 'require_last_table', 'local_tables',
                 'qualifiable')

    def __init__(self, table_refs=None, require_last_table=None,
                 local_tables=tuple(), qualifiable=False):
        self.table_refs = table_refs
        self.require_last_table = require_last_table
        self.local_tables = local_tables
        self.qualifiable = qualifiable


class Keyword(Suggestion):
    __slots__ = ()


class NamedQuery(Suggestion):
    __slots__ = ()


class Datatype(Suggestion):

    __slots__ = ('schema',)

    def __init__(self, schema):
        self.schema = schema


class Alias(Suggestion):

    __slots__ = ('aliases',)

    def __init__(self, aliases):
        self.aliases = aliases


class Path(Suggestion):
    __slots__ = ()

