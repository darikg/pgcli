import re
from collections import defaultdict


class KeywordCounter(object):
    def __init__(self, keywords):
        self.regexes = dict((kw, _compile_regex(kw)) for kw in keywords)
        self.counts = defaultdict(int)

    def update(self, text):
        for keyword, regex in self.regexes.items():
            for _ in regex.finditer(text):
                self.counts[keyword] += 1

    def __getitem__(self, item):
        return self.counts[item]

white_space_regex = re.compile('\\s+', re.MULTILINE)


def _compile_regex(keyword):
    # Surround the keyword with word boundaries and replace interior whitepsace
    # with whitespace wildcards
    pattern = '\\b' + re.sub(white_space_regex, '\\s+', keyword) + '\\b'
    return re.compile(pattern, re.MULTILINE | re.IGNORECASE)
