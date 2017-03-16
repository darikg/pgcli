class Match(object):
    def __init__(self, completion, priority):
        self.completion = completion
        self.priority = priority


class SchemaObject(object):
    def __init__(self, name, schema=None, function=False):
        self.name = name
        self.schema = schema
        self.function = function


class Candidate(object):
    def __init__(self, completion, prio, meta, synonyms=None, prio2=None):
        self.completion = completion
        self.prio = prio
        self.meta = meta
        self.synonyms = synonyms or [completion]
        self.prio2 = prio2



