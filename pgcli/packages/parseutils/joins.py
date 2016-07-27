from collections import defaultdict, namedtuple

Column = namedtuple('Column', 'schema tbl col')


def list_dict(pairs):
    """ Turns [(a, b), (a, c)] into {a: [b, c]}
    """
    d = defaultdict(list)
    for pair in pairs:
        d[pair[0]].append(pair[1])
    return d


def iter_fk_join_conditions(lcols):
    for lcol in lcols:
        for fk in lcol.foreignkeys:
            yield fk, lcol.name