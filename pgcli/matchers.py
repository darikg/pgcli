from .packages.sqlcompletion import (FromClauseItem,
    suggest_type, Special, Database, Schema, Table, Function, Column, View,
    Keyword, NamedQuery, Datatype, Alias, Path, JoinCondition, Join)
from collections import namedtuple
from .config import load_config, config_location
from pgspecial.namedqueries import NamedQueries
from .matching import Candidate, SchemaObject, Match
from collections import namedtuple, defaultdict
from prompt_toolkit.contrib.completers import PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.completion import Completion
from .packages.parseutils.tables import TableReference
import operator
import logging
import re
from .packages.parseutils.utils import last_word

try:
    from collections import OrderedDict
except ImportError:
    from .packages.ordereddict import OrderedDict


NamedQueries.instance = NamedQueries.from_config(
    load_config(config_location() + 'config'))

_logger = logging.getLogger(__name__)

normalize_ref = lambda ref: ref if ref[0] == '"' else '"' + ref.lower() +  '"'

def generate_alias(tbl):
    """ Generate a table alias, consisting of all upper-case letters in
    the table name, or, if there are no upper-case letters, the first letter +
    all letters preceded by _
    param tbl - unescaped name of the table to alias
    """
    return ''.join([l for l in tbl if l.isupper()] or
        [l for l, prev in zip(tbl,  '_' + tbl) if prev == '_' and l != '_'])


_MATCHERS = dict()


def register_matcher(func, suggestion_type):
    _MATCHERS[suggestion_type] = func


def matches_suggestion(suggestion_type):
    def wrapper(wrapped):
        register_matcher(wrapped, suggestion_type)
        return wrapped
    return wrapper


def match_suggestions(completer, suggestions, word_before_cursor):
    matches = []

    for suggestion in suggestions:
        suggestion_type = type(suggestion)
        _logger.debug('Suggestion type: %r', suggestion_type)

        # Map suggestion type to method
        # e.g. 'table' -> self.get_table_matches
        matcher = _MATCHERS[suggestion_type]
        matches.extend(matcher(completer, suggestion, word_before_cursor))

    # Sort matches so highest priorities are first
    matches = sorted(matches, key=operator.attrgetter('priority'), reverse=True)
    return matches


@matches_suggestion(Join)
def get_join_matches(completer, suggestion, word_before_cursor):
    tbls = suggestion.table_refs
    cols = completer.populate_scoped_cols(tbls)
    # Set up some data structures for efficient access
    qualified = dict((normalize_ref(t.ref), t.schema) for t in tbls)
    ref_prio = dict((normalize_ref(t.ref), n) for n, t in enumerate(tbls))
    refs = set(normalize_ref(t.ref) for t in tbls)
    other_tbls = set((t.schema, t.name)
        for t in list(cols)[:-1])
    joins = []
    # Iterate over FKs in existing tables to find potential joins
    fks = ((fk, rtbl, rcol) for rtbl, rcols in cols.items()
        for rcol in rcols for fk in rcol.foreignkeys)
    col = namedtuple('col', 'schema tbl col')
    for fk, rtbl, rcol in fks:
        right = col(rtbl.schema, rtbl.name, rcol.name)
        child = col(fk.childschema, fk.childtable, fk.childcolumn)
        parent = col(fk.parentschema, fk.parenttable, fk.parentcolumn)
        left = child if parent == right else parent
        if suggestion.schema and left.schema != suggestion.schema:
            continue
        c = completer.case
        if completer.generate_aliases or normalize_ref(left.tbl) in refs:
            lref = completer.alias(left.tbl, suggestion.table_refs)
            join = '{0} {4} ON {4}.{1} = {2}.{3}'.format(
                c(left.tbl), c(left.col), rtbl.ref, c(right.col), lref)
        else:
            join = '{0} ON {0}.{1} = {2}.{3}'.format(
                c(left.tbl), c(left.col), rtbl.ref, c(right.col))
        alias = generate_alias(completer.case(left.tbl))
        synonyms = [join, '{0} ON {0}.{1} = {2}.{3}'.format(
            alias, c(left.col), rtbl.ref, c(right.col))]
        # Schema-qualify if (1) new table in same schema as old, and old
        # is schema-qualified, or (2) new in other schema, except public
        if not suggestion.schema and (qualified[normalize_ref(rtbl.ref)]
            and left.schema == right.schema
            or left.schema not in(right.schema, 'public')):
            join = left.schema + '.' + join
        prio = ref_prio[normalize_ref(rtbl.ref)] * 2 + (
            0 if (left.schema, left.tbl) in other_tbls else 1)
        joins.append(Candidate(join, prio, 'join', synonyms=synonyms))

    return completer.find_matches(word_before_cursor, joins, meta='join')


@matches_suggestion(JoinCondition)
def get_join_condition_matches(completer, suggestion, word_before_cursor):
    col = namedtuple('col', 'schema tbl col')
    tbls = completer.populate_scoped_cols(suggestion.table_refs).items
    cols = [(t, c) for t, cs in tbls() for c in cs]
    try:
        lref = (suggestion.parent or suggestion.table_refs[-1]).ref
        ltbl, lcols = [(t, cs) for (t, cs) in tbls() if t.ref == lref][-1]
    except IndexError: # The user typed an incorrect table qualifier
        return []
    conds, found_conds = [], set()

    def add_cond(lcol, rcol, rref, prio, meta):
        prefix = '' if suggestion.parent else ltbl.ref + '.'
        case = completer.case
        cond = prefix + case(lcol) + ' = ' + rref + '.' + case(rcol)
        if cond not in found_conds:
            found_conds.add(cond)
            conds.append(Candidate(cond, prio + ref_prio[rref], meta))

    def list_dict(pairs): # Turns [(a, b), (a, c)] into {a: [b, c]}
        d = defaultdict(list)
        for pair in pairs:
            d[pair[0]].append(pair[1])
        return d

    # Tables that are closer to the cursor get higher prio
    ref_prio = dict((tbl.ref, num) for num, tbl
        in enumerate(suggestion.table_refs))
    # Map (schema, table, col) to tables
    coldict = list_dict(((t.schema, t.name, c.name), t)
        for t, c in cols if t.ref != lref)
    # For each fk from the left table, generate a join condition if
    # the other table is also in the scope
    fks = ((fk, lcol.name) for lcol in lcols for fk in lcol.foreignkeys)
    for fk, lcol in fks:
        left = col(ltbl.schema, ltbl.name, lcol)
        child = col(fk.childschema, fk.childtable, fk.childcolumn)
        par = col(fk.parentschema, fk.parenttable, fk.parentcolumn)
        left, right = (child, par) if left == child else (par, child)
        for rtbl in coldict[right]:
            add_cond(left.col, right.col, rtbl.ref, 2000, 'fk join')
    # For name matching, use a {(colname, coltype): TableReference} dict
    coltyp = namedtuple('coltyp', 'name datatype')
    col_table = list_dict((coltyp(c.name, c.datatype), t) for t, c in cols)
    # Find all name-match join conditions
    for c in (coltyp(c.name, c.datatype) for c in lcols):
        for rtbl in (t for t in col_table[c] if t.ref != ltbl.ref):
            prio = 1000 if c.datatype in (
                'integer', 'bigint', 'smallint') else 0
            add_cond(c.name, c.name, rtbl.ref, prio, 'name join')

    return completer.find_matches(word_before_cursor, conds, meta='join')


@matches_suggestion(Function)
def get_function_matches(completer, suggestion, word_before_cursor, alias=False):
    def _cand(func, alias):
        return _make_cand(completer, func, alias, suggestion)
    if suggestion.filter == 'for_from_clause':
        # Only suggest functions allowed in FROM clause
        filt = lambda f: not f.is_aggregate and not f.is_window
        funcs = [_cand(f, alias)
                 for f in completer.populate_functions(suggestion.schema, filt)]
    else:
        fs = completer.populate_schema_objects(suggestion.schema, 'functions')
        funcs = [_cand(f, alias=False) for f in fs]

    # Function overloading means we way have multiple functions of the same
    # name at this point, so keep unique names only
    funcs = set(funcs)

    funcs = completer.find_matches(word_before_cursor, funcs, meta='function')

    if not suggestion.schema and not suggestion.filter:
        # also suggest hardcoded functions using startswith matching
        predefined_funcs = completer.find_matches(
            word_before_cursor, completer.functions, mode='strict',
            meta='function')
        funcs.extend(predefined_funcs)

    return funcs


@matches_suggestion(Schema)
def get_schema_matches(completer, _, word_before_cursor):
    schema_names = completer.dbmetadata['tables'].keys()

    # Unless we're sure the user really wants them, hide schema names
    # starting with pg_, which are mostly temporary schemas
    if not word_before_cursor.startswith('pg_'):
        schema_names = [s for s in schema_names if not s.startswith('pg_')]

    return completer.find_matches(word_before_cursor, schema_names,
        meta='schema')


@matches_suggestion(FromClauseItem)
def get_from_clause_item_matches(completer, suggestion, word_before_cursor):
    alias = completer.generate_aliases
    s = suggestion
    t_sug = Table(s.schema, s.table_refs, s.local_tables)
    v_sug = View(s.schema, s.table_refs)
    f_sug = Function(s.schema, s.table_refs, filter='for_from_clause')
    return (get_table_matches(completer, t_sug, word_before_cursor, alias)
        + get_view_matches(completer, v_sug, word_before_cursor, alias)
        + get_function_matches(completer, f_sug, word_before_cursor, alias))


# Note: tbl is a SchemaObject
def _make_cand(completer, tbl, do_alias, suggestion):
    cased_tbl = completer.case(tbl.name)
    if do_alias:
        alias = completer.alias(cased_tbl, suggestion.table_refs)
    synonyms = (cased_tbl, generate_alias(cased_tbl))
    maybe_parens = '()' if tbl.function else ''
    maybe_alias = (' ' + alias) if do_alias else ''
    maybe_schema = (completer.case(tbl.schema) + '.') if tbl.schema else ''
    item = maybe_schema + cased_tbl + maybe_parens + maybe_alias
    prio2 = 0 if tbl.schema else 1
    return Candidate(item, synonyms=synonyms, prio2=prio2)


@matches_suggestion(Table)
def get_table_matches(completer, suggestion, word_before_cursor, alias=False):
    tables = completer.populate_schema_objects(suggestion.schema, 'tables')
    tables.extend(SchemaObject(tbl.name) for tbl in suggestion.local_tables)

    # Unless we're sure the user really wants them, don't suggest the
    # pg_catalog tables that are implicitly on the search path
    if not suggestion.schema and (
            not word_before_cursor.startswith('pg_')):
        tables = [t for t in tables if not t.name.startswith('pg_')]
    tables = [_make_cand(completer, t, alias, suggestion) for t in tables]
    return completer.find_matches(word_before_cursor, tables, meta='table')


@matches_suggestion(View)
def get_view_matches(completer, suggestion, word_before_cursor, alias=False):
    views = completer.populate_schema_objects(suggestion.schema, 'views')

    if not suggestion.schema and (
            not word_before_cursor.startswith('pg_')):
        views = [v for v in views if not v.name.startswith('pg_')]
    views = [_make_cand(completer, v, alias, suggestion) for v in views]
    return completer.find_matches(word_before_cursor, views, meta='view')


@matches_suggestion(Alias)
def get_alias_matches(completer, suggestion, word_before_cursor):
    aliases = suggestion.aliases
    return completer.find_matches(word_before_cursor, aliases,
                             meta='table alias')


@matches_suggestion(Database)
def get_database_matches(completer, _, word_before_cursor):
    return completer.find_matches(word_before_cursor, completer.databases,
                             meta='database')


@matches_suggestion(Keyword)
def get_keyword_matches(completer, _, word_before_cursor):
    casing = completer.keyword_casing
    if casing == 'auto':
        if word_before_cursor and word_before_cursor[-1].islower():
            casing = 'lower'
        else:
            casing = 'upper'

    if casing == 'upper':
        keywords = [k.upper() for k in completer.keywords]
    else:
        keywords = [k.lower() for k in completer.keywords]

    return completer.find_matches(word_before_cursor, keywords,
                             mode='strict', meta='keyword')


@matches_suggestion(Path)
def get_path_matches(completer, _, word_before_cursor):
    completer = PathCompleter(expanduser=True)
    document = Document(text=word_before_cursor,
                        cursor_position=len(word_before_cursor))
    for c in completer.get_completions(document, None):
        yield Match(completion=c, priority=(0,))


@matches_suggestion(Special)
def get_special_matches(completer, _, word_before_cursor):
    if not completer.pgspecial:
        return []

    commands = completer.pgspecial.commands
    cmds = commands.keys()
    cmds = [Candidate(cmd, 0, commands[cmd].description) for cmd in cmds]
    return completer.find_matches(word_before_cursor, cmds, mode='strict')


@matches_suggestion(Datatype)
def get_datatype_matches(completer, suggestion, word_before_cursor):
    # suggest custom datatypes
    types = completer.populate_schema_objects(suggestion.schema, 'datatypes')
    types = [_make_cand(completer, t, False, suggestion) for t in types]
    matches = completer.find_matches(word_before_cursor, types, meta='datatype')

    if not suggestion.schema:
        # Also suggest hardcoded types
        matches.extend(completer.find_matches(word_before_cursor, completer.datatypes,
                                         mode='strict', meta='datatype'))

    return matches


@matches_suggestion(NamedQuery)
def get_namedquery_matches(completer, _, word_before_cursor):
    return completer.find_matches(
        word_before_cursor, NamedQueries.instance.list(), meta='named query')


@matches_suggestion(Column)
def get_column_matches(completer, suggestion, word_before_cursor):
        tables = suggestion.table_refs
        do_qualify = suggestion.qualifiable and {'always': True, 'never': False,
            'if_more_than_one_table': len(tables) > 1}[completer.qualify_columns]
        qualify = lambda col, tbl: (
            (tbl + '.' + completer.case(col)) if do_qualify else completer.case(col))
        _logger.debug("Completion column scope: %r", tables)
        scoped_cols = completer.populate_scoped_cols(tables, suggestion.local_tables)

        colit = scoped_cols.items
        def make_cand(name, ref):
            synonyms = (name, generate_alias(completer.case(name)))
            return Candidate(qualify(name, ref), 0, 'column', synonyms)
        flat_cols = []
        for t, cols in colit():
            for c in cols:
                flat_cols.append(make_cand(c.name, t.ref))
        if suggestion.require_last_table:
            # require_last_table is used for 'tb11 JOIN tbl2 USING (...' which should
            # suggest only columns that appear in the last table and one more
            ltbl = tables[-1].ref
            flat_cols = list(
              set(c.name for t, cs in colit() if t.ref == ltbl for c in cs) &
              set(c.name for t, cs in colit() if t.ref != ltbl for c in cs))
        lastword = last_word(word_before_cursor, include='most_punctuations')
        if lastword == '*':
            if completer.asterisk_column_order == 'alphabetic':
                flat_cols.sort()
                for cols in scoped_cols.values():
                    cols.sort(key=operator.attrgetter('name'))
            if (lastword != word_before_cursor and len(tables) == 1
              and word_before_cursor[-len(lastword) - 1] == '.'):
                # User typed x.*; replicate "x." for all columns except the
                # first, which gets the original (as we only replace the "*"")
                sep = ', ' + word_before_cursor[:-1]
                collist = sep.join(completer.case(c.completion) for c in flat_cols)
            else:
                collist = ', '.join(qualify(c.name, t.ref)
                    for t, cs in colit() for c in cs)

            return [Match(completion=Completion(collist, -1,
                display_meta='columns', display='*'), priority=(1,1,1))]

        return completer.find_matches(word_before_cursor, flat_cols,
            meta='column')


def find_matches(completer, text, collection, mode='fuzzy', meta=None):
    """Find completion matches for the given text.

    Given the user's input text and a collection of available
    completions, find completions matching the last word of the
    text.

    `collection` can be either a list of strings or a list of Candidate
    namedtuples.
    `mode` can be either 'fuzzy', or 'strict'
        'fuzzy': fuzzy matching, ties broken by name prevalance
        `keyword`: start only matching, ties broken by keyword prevalance

    yields prompt_toolkit Completion instances for any matches found
    in the collection of available completions.

    """
    if not collection:
        return []
    prio_order = [
        'keyword', 'function', 'view', 'table', 'datatype', 'database',
        'schema', 'column', 'table alias', 'join', 'name join', 'fk join'
    ]
    type_priority = prio_order.index(meta) if meta in prio_order else -1
    text = last_word(text, include='most_punctuations').lower()
    text_len = len(text)

    if text and text[0] == '"':
        # text starts with double quote; user is manually escaping a name
        # Match on everything that follows the double-quote. Note that
        # text_len is calculated before removing the quote, so the
        # Completion.position value is correct
        text = text[1:]

    if mode == 'fuzzy':
        fuzzy = True
        priority_func = completer.prioritizer.name_count
    else:
        fuzzy = False
        priority_func = completer.prioritizer.keyword_count

    # Construct a `_match` function for either fuzzy or non-fuzzy matching
    # The match function returns a 2-tuple used for sorting the matches,
    # or None if the item doesn't match
    # Note: higher priority values mean more important, so use negative
    # signs to flip the direction of the tuple
    if fuzzy:
        regex = '.*?'.join(map(re.escape, text))
        pat = re.compile('(%s)' % regex)

        def _match(item):
            if item.lower()[:len(text) + 1] in (text, text + ' '):
                # Exact match of first word in suggestion
                # This is to get exact alias matches to the top
                # E.g. for input `e`, 'Entries E' should be on top
                # (before e.g. `EndUsers EU`)
                return float('Infinity'), -1
            r = pat.search(completer.unescape_name(item.lower()))
            if r:
                return -len(r.group()), -r.start()
    else:
        match_end_limit = len(text)

        def _match(item):
            match_point = item.lower().find(text, 0, match_end_limit)
            if match_point >= 0:
                # Use negative infinity to force keywords to sort after all
                # fuzzy matches
                return -float('Infinity'), -match_point

    matches = []
    for cand in collection:
        if isinstance(cand, Candidate):
            item, prio, display_meta, synonyms, prio2 = cand
            if display_meta is None:
                display_meta = meta
            syn_matches = (_match(x) for x in synonyms)
            # Nones need to be removed to avoid max() crashing in Python 3
            syn_matches = [m for m in syn_matches if m]
            sort_key = max(syn_matches) if syn_matches else None
        else:
            item, display_meta, prio, prio2 = cand, meta, 0, 0
            sort_key = _match(cand)

        if sort_key:
            if display_meta and len(display_meta) > 50:
                # Truncate meta-text to 50 characters, if necessary
                display_meta = display_meta[:47] + u'...'

            # Lexical order of items in the collection, used for
            # tiebreaking items with the same match group length and start
            # position. Since we use *higher* priority to mean "more
            # important," we use -ord(c) to prioritize "aa" > "ab" and end
            # with 1 to prioritize shorter strings (ie "user" > "users").
            # We first do a case-insensitive sort and then a
            # case-sensitive one as a tie breaker.
            # We also use the unescape_name to make sure quoted names have
            # the same priority as unquoted names.
            lexical_priority = (tuple(0 if c in(' _') else -ord(c)
                for c in completer.unescape_name(item.lower())) + (1,)
                + tuple(c for c in item))

            item = completer.case(item)
            priority = (
                sort_key, type_priority, prio, priority_func(item),
                prio2, lexical_priority
            )

            matches.append(Match(
                completion=Completion(item, -text_len,
                display_meta=display_meta),
                priority=priority))
    return matches


def alias(completer, tbl, tbls):
    """ Generate a unique table alias
    tbl - name of the table to alias, quoted if it needs to be
    tbls - TableReference iterable of tables already in query
    """
    tbl = completer.case(tbl)
    tbls = set(normalize_ref(t.ref) for t in tbls)
    if completer.generate_aliases:
        tbl = generate_alias(completer.unescape_name(tbl))
    if normalize_ref(tbl) not in tbls:
        return tbl
    elif tbl[0] == '"':
        aliases = ('"' + tbl[1:-1] + str(i) + '"' for i in count(2))
    else:
        aliases = (tbl + str(i) for i in count(2))
    return next(a for a in aliases if normalize_ref(a) not in tbls)



def populate_scoped_cols(completer, scoped_tbls, local_tbls=()):
    """ Find all columns in a set of scoped_tables
    :param scoped_tbls: list of TableReference namedtuples
    :param local_tbls: tuple(TableMetadata)
    :return: {TableReference:{colname:ColumnMetaData}}
    """
    ctes = dict((normalize_ref(t.name), t.columns) for t in local_tbls)
    columns = OrderedDict()
    meta = completer.dbmetadata

    def addcols(schema, rel, alias, reltype, cols):
        tbl = TableReference(schema, rel, alias, reltype == 'functions')
        if tbl not in columns:
            columns[tbl] = []
        columns[tbl].extend(cols)

    for tbl in scoped_tbls:
        # Local tables should shadow database tables
        if tbl.schema is None and normalize_ref(tbl.name) in ctes:
            cols = ctes[normalize_ref(tbl.name)]
            addcols(None, tbl.name, 'CTE', tbl.alias, cols)
            continue
        schemas = [tbl.schema] if tbl.schema else completer.search_path
        for schema in schemas:
            relname = completer.escape_name(tbl.name)
            schema = completer.escape_name(schema)
            if tbl.is_function:
            # Return column names from a set-returning function
            # Get an array of FunctionMetadata objects
                functions = meta['functions'].get(schema, {}).get(relname)
                for func in (functions or []):
                    # func is a FunctionMetadata object
                    cols = func.fields()
                    addcols(schema, relname, tbl.alias, 'functions', cols)
            else:
                for reltype in ('tables', 'views'):
                    cols = meta[reltype].get(schema, {}).get(relname)
                    if cols:
                        cols = cols.values()
                        addcols(schema, relname, tbl.alias, reltype, cols)
                        break

    return columns


def _get_schemas(completer, obj_typ, schema):
    """ Returns a list of schemas from which to suggest objects
    schema is the schema qualification input by the user (if any)
    """
    metadata = completer.dbmetadata[obj_typ]
    if schema:
        schema = completer.escape_name(schema)
        return [schema] if schema in metadata else []
    return completer.search_path if completer.search_path_filter else metadata.keys()


def _maybe_schema(completer, schema, parent):
    return None if parent or schema in completer.search_path else schema


def populate_schema_objects(completer, schema, obj_type):
    """Returns a list of SchemaObjects representing tables, views, funcs
    schema is the schema qualification input by the user (if any)
    """

    return [
        SchemaObject(
            name=obj,
            schema=(_maybe_schema(completer, schema=sch, parent=schema)),
            function=(obj_type == 'functions')
        )
        for sch in _get_schemas(completer, obj_type, schema)
        for obj in completer.dbmetadata[obj_type][sch].keys()
    ]


def populate_functions(completer, schema, filter_func):
    """Returns a list of function names

    filter_func is a function that accepts a FunctionMetadata namedtuple
    and returns a boolean indicating whether that function should be
    kept or discarded
    """

    # Because of multiple dispatch, we can have multiple functions
    # with the same name, which is why `for meta in metas` is necessary
    # in the comprehensions below
    return [
        SchemaObject(
            name=func,
            schema=(_maybe_schema(completer, schema=sch, parent=schema)),
            function=True
        )
        for sch in _get_schemas(completer, 'functions', schema)
        for (func, metas) in completer.dbmetadata['functions'][sch].items()
        for meta in metas
        if filter_func(meta)
    ]
