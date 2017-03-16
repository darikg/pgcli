from __future__ import print_function, unicode_literals
import logging
import re
from itertools import count, repeat
import operator
from collections import namedtuple, defaultdict
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.contrib.completers import PathCompleter
from prompt_toolkit.document import Document
from .packages.sqlcompletion import suggest_type
from .packages.parseutils.meta import ColumnMetadata, ForeignKey
from .packages.parseutils.utils import last_word
from .packages.parseutils.tables import TableReference
from .packages.pgliterals.main import get_literals
from .packages.prioritization import PrevalenceCounter
from .matchers import match_suggestions, find_matches

try:
    from collections import OrderedDict
except ImportError:
    from .packages.ordereddict import OrderedDict

_logger = logging.getLogger(__name__)


class PGCompleter(Completer):
    keywords = get_literals('keywords')
    functions = get_literals('functions')
    datatypes = get_literals('datatypes')

    def __init__(self, smart_completion=True, pgspecial=None, settings=None):
        super(PGCompleter, self).__init__()
        self.smart_completion = smart_completion
        self.pgspecial = pgspecial
        self.prioritizer = PrevalenceCounter()
        settings = settings or {}
        self.search_path_filter = settings.get('search_path_filter')
        self.generate_aliases = settings.get('generate_aliases')
        self.casing_file = settings.get('casing_file')
        self.generate_casing_file = settings.get('generate_casing_file')
        self.qualify_columns = settings.get(
            'qualify_columns', 'if_more_than_one_table')
        self.asterisk_column_order = settings.get(
            'asterisk_column_order', 'table_order')

        keyword_casing = settings.get('keyword_casing', 'upper').lower()
        if keyword_casing not in ('upper', 'lower', 'auto'):
            keyword_casing = 'upper'
        self.keyword_casing = keyword_casing

        self.reserved_words = set()
        for x in self.keywords:
            self.reserved_words.update(x.split())
        self.name_pattern = re.compile("^[_a-z][_a-z0-9\$]*$")

        self.databases = []
        self.dbmetadata = {'tables': {}, 'views': {}, 'functions': {},
                           'datatypes': {}}
        self.search_path = []
        self.casing = {}

        self.all_completions = set(self.keywords + self.functions)

    def escape_name(self, name):
        if name and ((not self.name_pattern.match(name))
                or (name.upper() in self.reserved_words)
                or (name.upper() in self.functions)):
            name = '"%s"' % name

        return name

    def unescape_name(self, name):
        """ Unquote a string."""
        if name and name[0] == '"' and name[-1] == '"':
            name = name[1:-1]

        return name

    def escaped_names(self, names):
        return [self.escape_name(name) for name in names]

    def extend_database_names(self, databases):
        databases = self.escaped_names(databases)
        self.databases.extend(databases)

    def extend_keywords(self, additional_keywords):
        self.keywords.extend(additional_keywords)
        self.all_completions.update(additional_keywords)

    def extend_schemata(self, schemata):

        # schemata is a list of schema names
        schemata = self.escaped_names(schemata)
        metadata = self.dbmetadata['tables']
        for schema in schemata:
            metadata[schema] = {}

        # dbmetadata.values() are the 'tables' and 'functions' dicts
        for metadata in self.dbmetadata.values():
            for schema in schemata:
                metadata[schema] = {}

        self.all_completions.update(schemata)

    def extend_casing(self, words):
        """ extend casing data

        :return:
        """
        # casing should be a dict {lowercasename:PreferredCasingName}
        self.casing = dict((word.lower(), word) for word in words)

    def extend_relations(self, data, kind):
        """ extend metadata for tables or views

        :param data: list of (schema_name, rel_name) tuples
        :param kind: either 'tables' or 'views'
        :return:
        """

        data = [self.escaped_names(d) for d in data]

        # dbmetadata['tables']['schema_name']['table_name'] should be an
        # OrderedDict {column_name:ColumnMetaData}.
        metadata = self.dbmetadata[kind]
        for schema, relname in data:
            try:
                metadata[schema][relname] = OrderedDict()
            except KeyError:
                _logger.error('%r %r listed in unrecognized schema %r',
                              kind, relname, schema)
            self.all_completions.add(relname)

    def extend_columns(self, column_data, kind):
        """ extend column metadata

        :param column_data: list of (schema_name, rel_name, column_name, column_type) tuples
        :param kind: either 'tables' or 'views'
        :return:
        """
        metadata = self.dbmetadata[kind]
        for schema, relname, colname, datatype in column_data:
            (schema, relname, colname) = self.escaped_names(
                [schema, relname, colname])
            column = ColumnMetadata(name=colname, datatype=datatype,
                foreignkeys=[])
            metadata[schema][relname][colname] = column
            self.all_completions.add(colname)

    def extend_functions(self, func_data):

        # func_data is a list of function metadata namedtuples
        # with fields schema_name, func_name, arg_list, result,
        # is_aggregate, is_window, is_set_returning

        # dbmetadata['schema_name']['functions']['function_name'] should return
        # the function metadata namedtuple for the corresponding function
        metadata = self.dbmetadata['functions']

        for f in func_data:
            schema, func = self.escaped_names([f.schema_name, f.func_name])

            if func in metadata[schema]:
                metadata[schema][func].append(f)
            else:
                metadata[schema][func] = [f]

            self.all_completions.add(func)

    def extend_foreignkeys(self, fk_data):

        # fk_data is a list of ForeignKey namedtuples, with fields
        # parentschema, childschema, parenttable, childtable,
        # parentcolumns, childcolumns

        # These are added as a list of ForeignKey namedtuples to the
        # ColumnMetadata namedtuple for both the child and parent
        meta = self.dbmetadata['tables']

        for fk in fk_data:
            e = self.escaped_names
            parentschema, childschema = e([fk.parentschema, fk.childschema])
            parenttable, childtable = e([fk.parenttable, fk.childtable])
            childcol, parcol = e([fk.childcolumn, fk.parentcolumn])
            childcolmeta =  meta[childschema][childtable][childcol]
            parcolmeta =  meta[parentschema][parenttable][parcol]
            fk = ForeignKey(parentschema, parenttable, parcol,
                childschema, childtable, childcol)
            childcolmeta.foreignkeys.append((fk))
            parcolmeta.foreignkeys.append((fk))

    def extend_datatypes(self, type_data):

        # dbmetadata['datatypes'][schema_name][type_name] should store type
        # metadata, such as composite type field names. Currently, we're not
        # storing any metadata beyond typename, so just store None
        meta = self.dbmetadata['datatypes']

        for t in type_data:
            schema, type_name = self.escaped_names(t)
            meta[schema][type_name] = None
            self.all_completions.add(type_name)

    def extend_query_history(self, text, is_init=False):
        if is_init:
            # During completer initialization, only load keyword preferences,
            # not names
            self.prioritizer.update_keywords(text)
        else:
            self.prioritizer.update(text)

    def set_search_path(self, search_path):
        self.search_path = self.escaped_names(search_path)

    def reset_completions(self):
        self.databases = []
        self.special_commands = []
        self.search_path = []
        self.dbmetadata = {'tables': {}, 'views': {}, 'functions': {},
                           'datatypes': {}}
        self.all_completions = set(self.keywords + self.functions)

    def case(self, word):
        return self.casing.get(word, word)

    def get_completions(self, document, complete_event, smart_completion=None):
        word_before_cursor = document.get_word_before_cursor(WORD=True)

        if smart_completion is None:
            smart_completion = self.smart_completion

        # If smart_completion is off then match any word that starts with
        # 'word_before_cursor'.
        if not smart_completion:
            matches = find_matches(word_before_cursor, self.all_completions,
                                        mode='strict')
            completions = [m.completion for m in matches]
            return sorted(completions, key=operator.attrgetter('text'))

        suggestions = suggest_type(document.text, document.text_before_cursor)
        matches = match_suggestions(suggestions, document.text_before_cursor)
        return [m.completion for m in matches]




