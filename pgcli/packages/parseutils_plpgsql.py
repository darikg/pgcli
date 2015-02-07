import re
import sqlparse

declaration_block_regex = re.compile(r'\bDECLARE\b(.*?)\bBEGIN\b',
                                    re.DOTALL | re.IGNORECASE)


def function_variable_names(sql):
    """Yields variable names declared in a plpgsql function declaration block"""
    sql = extract_declaration_block(sql)
    return declaration_block_variable_names(sql) if sql else ()


def extract_declaration_block(sql):
    m = declaration_block_regex.search(sql)
    return m.group(1) if m else None


def declaration_block_variable_names(block_sql):
    parsed = sqlparse.parse(block_sql)
    for stmt in parsed:
        # Can't really trust sql parse to correctly group plpgsql tokens
        # so just grab the first token, which should be the variable name
        stmt.tokens = list(stmt.flatten())
        first_name_tok = stmt.token_next_by_type(0, sqlparse.tokens.Name)
        if first_name_tok:
            yield first_name_tok.value


def test_function_variable_names():
    sql = '''
        DECLARE
            x int default 2;
            yyy text[] := ARRAY["asd", "sadasdasd"];
            z_z double precision default 5.0;
        BEGIN
            asdasd
            asdasd
            asdasd
        END'''

    assert tuple(function_variable_names(sql)) == ('x', 'yyy', 'z_z')


def test_extract_declaration_block():
    sql = '''
        DECLARE
            x int default 2;
            y text;
        BEGIN
            asdasd
            asdasd
            asdasd
        END'''

    block = '''
            x int default 2;
            y text;'''

    result = extract_declaration_block(sql)
    assert result.strip() == block.strip()


