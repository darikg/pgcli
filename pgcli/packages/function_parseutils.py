import re
import sqlparse
from sqlparse.tokens import Keyword, Token
from sqlparse.sql import Identifier, Function


create_function_regex = re.compile(r'^CREATE\s*(?:OR\s*REPLACE\s*)?FUNCTION',
                                   flags=re.IGNORECASE)

dollar_quote_regex = re.compile(r'^\$[^$]*\$$')

def is_function_def(sql):
    """Returns truthy if the sql statement defines a function"""
    return create_function_regex.match(sql)


def delineate_function_body(sql):
    """Returns (start, stop) indices of the function body in the sql string"""

    parsed = sqlparse.parse(sql)[0]

    # The `AS` keyword will sometimes trick sqlparse into thinking an alias is
    # being assigned, which causes the Function token to get grouped under an
    # Identifier tokenlist, which is a pain, so flatten all grouped tokens
    parsed = sqlparse.sql.Statement(list(parsed.flatten()))

    # The function body should immediately follow 'AS'
    as_kwd = parsed.token_next_match(0, Keyword, 'as')
    if not as_kwd:
        return None, None

    as_idx = parsed.token_index(as_kwd)

    start, stop = find_function_body_as_string_literal(parsed, as_idx)
    if not start:
        start, stop = find_function_body_as_ungrouped_tokens(parsed, as_idx)

    if start and not stop:
        # Presumably missing the closing quote
        stop = len(sql)

    return start, stop


def find_function_body_as_string_literal(parsed, search_idx):
    """
    :param parsed: sqlparse.sql.Statement object representing the function def
    :param search_idx: token index of where to start search
    :return: Tuple of indices (start, stop) delineating the function body
    """
    literal = parsed.token_next_by_type(search_idx, Token.Literal.String)
    if not literal:
        return None, None

    start = tok_start_pos(parsed, literal) + 1
    body = literal.value[1:-1]
    stop = start + len(body)

    return start, stop


def find_function_body_as_ungrouped_tokens(parsed, search_idx):
    """
    :param parsed: sqlparse.sql.Statement object representing the function def
    :param search_idx: token index of where to start search
    :return: Tuple of indices (start, stop) delineating the function body
    """

    tokens = list(parsed.flatten())

    for (i, tok1) in enumerate(tokens[search_idx+1:], search_idx+1):

        # Look for an opening $$dollar quote$$
        if (tok1.ttype in Token.Name.Builtin
                and dollar_quote_regex.match(tok1.value)):

            start = total_tok_len(tokens[:i+1])

            # Look for a matching closing dollar quote
            for (j, tok2) in enumerate(tokens[i+1:], i+1):
                if tok2.match(Token.Name.Builtin, tok1.value):
                    stop = start + total_tok_len(tokens[i+1:j])
                    break
            else:
                stop = None

            return start, stop

        elif tok1.match(Token.Error, "'"):
            # A single unclosed quote is parsed as an error
            # Don't bother looking for the closing quote, since there isn't one
            start = total_tok_len(tokens[:i+1])
            return start, None

    return None, None


def total_tok_len(tokens):
    """Sum the length of the raw strings of an array of sqlparse Tokens"""
    return sum(len(t.to_unicode()) for t in tokens)


def tok_start_pos(parent, child):
    """Calculate the start position of an sqlparse Token within its parent"""
    child_idx = parent.token_index(child)
    return total_tok_len(parent.tokens[:child_idx])