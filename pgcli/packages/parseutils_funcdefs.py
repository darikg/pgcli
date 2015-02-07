import re
import sqlparse
from sqlparse.tokens import (
    Keyword, Token, Whitespace, Comment, Punctuation, Name)
from sqlparse.sql import Identifier, Function


create_func_regex = re.compile(r'^CREATE\s*(?:OR\s*REPLACE\s*)?FUNCTION',
                               flags=re.IGNORECASE)

do_regex = re.compile(r'^DO\s*((?:LANGUAGE\s*)(\w+))?',
                      flags=re.IGNORECASE)


def is_nonsql_language(sql):
    return match_function_def(sql) or match_do_block(sql)[0]


def match_function_def(sql):
    return create_func_regex.match(sql)


def match_do_block(sql):
    """Returns (is_do_block, do_block_language) --> (Bool, String)"""
    match = do_regex.match(sql)
    if match:
        language = match.group(2) or 'plpgsql'
        return True, language
    else:
        return False, None


def parse_function_def(sql):
    parsed = sqlparse.parse(sql)[0]
    idx = parsed.token_index

    empty_result = [None] * 5

    # The function signature should immediately follow the FUNCTION keyword
    function_kwd = parsed.token_next_match(0, Keyword, 'function')
    sig_tok = parsed.token_next(idx(function_kwd))
    if not sig_tok:
        return empty_result

    start = stop = None
    if isinstance(sig_tok, Function):
        signature = sig_tok
    elif isinstance(sig_tok, Identifier):
        signature, start, stop = parse_identifier_as_signature(parsed, sig_tok)
    else:
        # No function signature -- give up
        return empty_result

    # Extract input parameter names from signature
    func_name = signature.get_name()
    parens = signature.tokens[1]
    arg_list = tuple(parens.flatten())[1:-1]
    arg_names = tuple(argument_names(arg_list))

    # Try to figure out what language the function is written in
    language_kwd = parsed.token_next_match(idx(sig_tok), Keyword, 'language')
    if language_kwd:
        language = parsed.token_next(idx(language_kwd))
        language = language.value.lower() if language.value else None
    else:
        language = None

    # Find the extent of the function body in terms of string indices
    if not start:
        start, stop = find_function_body_as_string_literal(parsed, sig_tok)
        if not start:
            start, stop = find_function_body_dollar_quoted(parsed)

    if start and not stop:
        # Presumably the closing punctuation not written yet
        stop = len(sql)

    return func_name, arg_names, language, start, stop


def parse_identifier_as_signature(parsed, sig_tok):
    """Returns tuple (FunctionToken, body_start, body_end"""

    # sqlparse incorectly (?) thinks that
    #       function_name(argument_list) as 'function_body'"
    # is an aliased identifier
    signature = sig_tok.tokens[0]

    # String quoted function body should be correctly extracted as an alias
    # Dollar quoted bodies aren't
    body = sig_tok.get_alias()
    if not body or body[0] == '$':
        return signature, None, None

    body_tok = sig_tok.token_next_by_type(0, Token.Literal.String)
    start = tok_start_pos(parsed, sig_tok) + tok_start_pos(sig_tok, body_tok) + 1
    stop = start + len(body)

    return signature, start, stop


def find_function_body_as_string_literal(parsed, sig_tok):
    literal = parsed.token_next_by_type(parsed.token_index(sig_tok),
                                        Token.Literal.String)
    if not literal:
        return None, None

    body = literal.value[1:-1]
    start = tok_start_pos(parsed, literal) + 1
    stop = start + len(body)

    return start, stop


def find_function_body_dollar_quoted(parsed):

    # Look for the function body as a dollar quoted string
    parsed.tokens = list(parsed.flatten())
    idx = parsed.token_index
    token_next_match = parsed.token_next_match

    # Find the first "$$" or "$tag$" delimeter
    delim1 = token_next_match(0, Token.Name.Builtin, r'^\$[^$]*\$$', regex=True)
    if not delim1:
        return None, None

    delim2 = token_next_match(idx(delim1)+1, Token.Name.Builtin, delim1.value)
    start = total_tok_len(parsed.tokens[:idx(delim1)+1])
    stop = total_tok_len(parsed.tokens[:idx(delim2)]) if delim2 else None

    return start, stop


def argument_names(tokens):
    """Parses function signature parameter tokens, yielding argument names"""

    # postgres argument list syntax:
    #   " ( [ [ argmode ] [ argname ] argtype
    #               [ { DEFAULT | = } default_expr ] [, ...] ] )"

    found_name = False
    parens = 0

    for tok in tokens:

        if tok.ttype in Whitespace or tok.ttype in Comment:
            continue

        if tok.ttype in Keyword:
            if tok.value.upper() not in ('IN', 'OUT', 'INOUT', 'VARIADIC'):
                # No other keywords allowed before arg name
                found_name = True
            continue

        if tok.ttype in Punctuation:
            if tok.value in ('(', '['):
                parens += 1
            elif tok.value in (')', ']'):
                parens -= 1
            elif tok.value == '=':
                # Setting default for current argument - name already occured
                found_name = True
            elif parens == 0 and tok.value == ',':
                # Must be end of the current argument spec
                found_name = False
            continue

        if not found_name and tok.ttype in Name:
            yield tok.value
            found_name = True


def total_tok_len(tokens):
    """Sum the length of the raw strings of an array of sqlparse Tokens"""
    return sum(len(t.to_unicode()) for t in tokens)


def tok_start_pos(parent, child):
    """Calculate the start position of an sqlparse Token within it's parrent"""
    return total_tok_len(parent.tokens[:parent.token_index(child)])


def test_is_function_def():
    assert match_function_def('CREATE FUNCTION myfunc as $$ asdasdasdasd$$')
    assert match_function_def('create \n or replace function myfunc asdasdsad')
    assert not match_function_def('select * from create function ')


def test_argument_names_simple():
    sql = '(x int, y int, z int)'
    tokens = list(sqlparse.parse(sql)[0].tokens[0].flatten())[1:-1]
    assert tuple(argument_names(tokens)) == ('x', 'y', 'z')

def test_argument_names_default_keyword():
    sql = '(x int, y int default 2, z int)'
    tokens = list(sqlparse.parse(sql)[0].tokens[0].flatten())[1:-1]
    assert tuple(argument_names(tokens)) == ('x', 'y', 'z')

def test_argument_names_default_equals():
    sql = '(x int, y int = 2, z int)'
    tokens = list(sqlparse.parse(sql)[0].tokens[0].flatten())[1:-1]
    assert tuple(argument_names(tokens)) == ('x', 'y', 'z')

def test_argument_names_argmodes():
    sql = '(in x int, out y int = 2, out z int)'
    tokens = list(sqlparse.parse(sql)[0].tokens[0].flatten())[1:-1]
    assert tuple(argument_names(tokens)) == ('x', 'y', 'z')

def test_extract_function_simple_language_last():
    sql = "CREATE FUNCTION f1() AS 'select what' LANGUAGE SQL"
    assert parse_function_def(sql) == (
        'f1', (), 'sql',
        len("CREATE FUNCTION f1() AS '"),
        len("CREATE FUNCTION f1() AS 'select what"))

def test_extract_function_simple_language_first():
    sql = "CREATE FUNCTION f1() LANGUAGE SQL AS 'select what'"
    assert parse_function_def(sql) == (
        'f1', (), 'sql',
        len("CREATE FUNCTION f1() LANGUAGE SQL AS '"),
        len("CREATE FUNCTION f1() LANGUAGE SQL AS 'select what"))

def test_extract_function_simple_dollar_quoted_language_last():
    sql = "CREATE FUNCTION f1() AS $$select what$$ LANGUAGE SQL"
    assert parse_function_def(sql) == (
        'f1', (), 'sql',
        len("CREATE FUNCTION f1() AS $$"),
        len("CREATE FUNCTION f1() AS $$select what"))

def test_extract_function_simple_dollar_quoted_language_first():
    sql = "CREATE FUNCTION f1() LANGUAGE SQL AS $$select what$$"
    assert parse_function_def(sql) == (
        'f1', (), 'sql',
        len("CREATE FUNCTION f1() LANGUAGE SQL AS $$"),
        len("CREATE FUNCTION f1() LANGUAGE SQL AS $$select what"))

def test_extract_function_arguments_simple():
    sql = "CREATE FUNCTION f1(x int, y text) AS 'select what' LANGUAGE SQL"
    assert parse_function_def(sql) == (
        'f1', ('x', 'y'), 'sql',
        len("CREATE FUNCTION f1(x int, y text) AS '"),
        len("CREATE FUNCTION f1(x int, y text) AS 'select what"))


