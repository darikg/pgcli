from sqlparse import parse
from sqlparse.tokens import Keyword, Whitespace
from sqlparse.sql import Identifier, IdentifierList, Parenthesis
from collections import namedtuple

# TableExpression is a namedtuple representing a CTE
# name: cte alias assigned in the query
# columns: list of column names
# start: index into the original string of the left parens starting the CTE
# stop: index into the original string of the right parens ending the CTE
TableExpression = namedtuple('TableExpression',
    ['name', 'columns', 'start', 'stop'])


def isolate_query_ctes(full_text, text_before_cursor):

    if not full_text:
        return full_text, text_before_cursor, ()

    ctes, remainder = extract_ctes(full_text)

    current_position = len(text_before_cursor)

    if not ctes:
        return full_text, text_before_cursor, ()

    for i, cte in enumerate(ctes):
        if cte.start < current_position < cte.stop:
            # Currently editing a cte
            text_before_cursor = full_text[cte.start:current_position]
            full_text = full_text[cte.start:cte.stop]
            return full_text, text_before_cursor, ctes[:i]

    # Editing past the last cte (ie the main body of the query)
    full_text = full_text[ctes[-1].stop:]
    text_before_cursor = text_before_cursor[ctes[-1].stop:current_position]
    return full_text, text_before_cursor, ctes


def extract_ctes(sql):
    """ Extract constant table expresseions from a query

        Returns tuple (ctes, remainder_sql)

        ctes is a list of TableExpression namedtuples
        remainder_sql is the text from the original query after the CTEs have
        been stripped.
    """

    p = parse(sql)[0]

    # Make sure the first meaningful token is "WITH" which is necessary to
    # define CTEs
    tok = get_first_meaningful_token(p.tokens)
    if not (tok and tok.ttype == Keyword and tok.value == 'WITH'):
        return [], sql

    idx = p.token_index(tok)

    # Get the next (meaningful) token, which should be the first CTE
    tok = p.token_next(idx)
    idx = p.token_index(tok)

    start_pos = token_start_pos(p.tokens, idx)
    ctes = []

    if isinstance(tok, IdentifierList):
        # Multiple ctes

        for t in tok.get_identifiers():
            cte_start_offset = token_start_pos(tok.tokens, tok.token_index(t))
            cte = get_cte_from_token(t, start_pos + cte_start_offset)

            if not cte:
                continue

            ctes.append(cte)

    elif isinstance(tok, Identifier):
        # A single CTE
        cte = get_cte_from_token(tok, start_pos)
        if cte:
            ctes.append(cte)

    idx = p.token_index(tok) + 1

    # Collapse everything after the ctes into a remainder query
    remainder = u''.join(tok.to_unicode() for tok in p.tokens[idx:])

    return ctes, remainder


def get_cte_from_token(tok, pos0):
    cte_name = tok.get_real_name()
    cte_query = tok.get_alias()
    if not cte_name or not cte_query:
        return None

    # Find the start position of the opening parenthesis
    parens = tok.token_next_by_instance(0, Parenthesis)
    if not parens:
        return None

    idx = tok.token_index(parens)
    start_pos = pos0 + token_start_pos(tok.tokens, idx)
    cte_len = len(parens.to_unicode())  # includes parens
    stop_pos = start_pos + cte_len

    cte_query = cte_query[1:-1]  # strip enclosing parens
    column_names = extract_column_names(cte_query)

    return TableExpression(cte_name, column_names, start_pos, stop_pos)


def extract_column_names(sql):
    p = parse(sql)[0]
    tok = get_first_meaningful_token(p.tokens)

    if tok.value.lower() == 'select':
        idx = p.token_index(tok)
        tok = p.token_next(idx)

        if isinstance(tok, IdentifierList):
            return tuple(t.get_name() for t in tok.get_identifiers()
                                        if isinstance(t, Identifier))
        elif isinstance(tok, Identifier):
            return tok.get_name(),

    # TODO: handle INSERT/UPDATE/DELETE ... RETURNING

    return ()


def get_first_meaningful_token(tokens):

    # Comments have ttype=None
    for tok in tokens:
        if tok.ttype and not tok.ttype == Whitespace:
            return tok


def token_start_pos(tokens, idx):
    return sum(len(t.to_unicode()) for t in tokens[:idx])









