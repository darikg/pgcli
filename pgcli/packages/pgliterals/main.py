import os
import json
import re

root = os.path.dirname(__file__)
literal_file = os.path.join(root, 'pgliterals.json')

with open(literal_file) as f:
    literals = json.load(f)


def get_literals(literal_type):
    """Where `literal_type` is one of 'keywords', 'functions', 'datatypes',
        returns a tuple of literal values of that type"""

    return tuple(literals[literal_type])


binary_operators = set(get_literals('binary_operators'))
binary_operator_regex = '|'.join(re.escape(op) for op in binary_operators)
binary_operator_regex = re.compile(binary_operator_regex)


def split_by_binary_operators(word):
    """
    >>> split_by_binary_operators('')
    ['']
    >>> split_by_binary_operators('foo')
    ['foo']
    >>> split_by_binary_operators('foo-bar')
    ['foo', 'bar']
    """
    return binary_operator_regex.split(word)

