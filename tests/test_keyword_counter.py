from pgcli.packages.keyword_counter import KeywordCounter


def test_keyword_counter():
    keywords = ['SELECT', 'GROUP BY']
    counter = KeywordCounter(keywords)
    sql = '''SELECT * FROM foo WHERE bar GROUP BY baz;
             select * from foo;
             SELECT * FROM foo WHERE bar GROUP
             BY baz'''
    counter.update(sql)

    counts = [counter[k] for k in keywords]
    assert counts == [3, 2]
    assert counter['FROM'] == 0

