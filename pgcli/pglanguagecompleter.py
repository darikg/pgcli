from itertools import chain
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from .packages.parseutils_funcdefs import parse_function_def, match_do_block
from .packages.parseutils_plpgsql import function_variable_names

try:
    # TODO: lazy import
    import jedi
except ImportError:
    jedi = None





class PGLanguageCompleter(Completer):

    # Keywords specific to CREATE FUNCTION
    create_func_keywords = {'AS', 'CALLED ON NULL INPUT', 'COST', 'CURRENT',
        'DEFAULT', 'DEFINER', 'EXTERNAL', 'FROM', 'IMMUTABLE', 'LANGUAGE',
        'RETURNS', 'RETURNS NULL ON NULL INPUT', 'ROWS',  'SECURITY', 'SET',
        'SETOF', 'STABLE', 'STRICT', 'TABLE', 'TO', 'VOLATILE', 'WINDOW',
        'WITH'}

    def __init__(self, pgcompleter):
        self.pgcompleter = pgcompleter  # the root pgcompleter
        self.completers = {}

        # plpgsql
        self.completers['plpgsql'] = PlpgsqlCompleter(pgcompleter)

        # plpython
        if jedi:
            pycompleter = PlpythonCompleter(pgcompleter)
            for lang in ('plpython', 'plpythonu', 'plpython2u', 'plpython3u'):
                self.completers[lang] = pycompleter

    def get_completions(self, document, complete_event):

        # First figure out if we're in a DO block or CREATE FUNCTION
        do_block, language = match_do_block(document.text)
        if do_block:
            func_name, arg_names, start, stop = None, (), 0, len(document.text)
        else:
            # Assume CREATE FUNCTION
            func_name, arg_names, language, start, stop = \
                parse_function_def(document.text)

        curr_pos = len(document.text_before_cursor)
        if do_block or (func_name and start and start < curr_pos <= stop):
            # User is currently editing function body

            if language in self.completers:
                document = Document(document.text[start:stop], curr_pos - start)
                return self.completers[language].get_completions(
                    document, complete_event, arg_names=arg_names)
            else:
                # Use standard pgcli autocompletion
                return self.pgcompleter.get_completions(
                    document, complete_event, nonsql_completion=False)

        else:
            # User editing outside the function body
            keywords = self.create_func_keywords | set(self.pgcompleter.keywords)
            return _find_matches(document.get_word_before_cursor(), keywords)


class PlpythonCompleter(Completer):
    def __init__(self, pgcompleter):
        super(self.__class__, self).__init__()
        self.pgcompleter = pgcompleter

    def get_completions(self, document, complete_event, arg_names=()):

        # Create a placeholder namespace dict holding function argument names
        # TODO: in theory, we know the type of each argument -- could set arg
        # value to placeholder of the same type so jedi could suggest
        # appropriate methods
        namespace = {arg: None for arg in arg_names}

        script = jedi.api.Interpreter(
            source=document.text,
            namespaces=[namespace],
            line=document.cursor_position_row + 1,
            column=document.cursor_position_col)

        for c in script.completions():
            yield Completion(c.complete)


class PlpgsqlCompleter(Completer):

    keywords = {'ALIAS', 'ARRAY', 'BEGIN', 'CONTINUE', 'CURSOR', 'DECLARE',
                'DEFINE', 'DIAGNOSTICS', 'ELSEIF', 'ELSIF', 'EXCEPTION',
                'EXECUTE', 'EXIT', 'FOREACH', 'FOUND', 'GET', 'LOOP', 'NEXT',
                'NOTICE', 'PERFORM', 'QUERY', 'RAISE', 'RETURN', 'RETURNING',
                'REVERSE', 'ROW_COUNT', 'SLICE', 'STRICT', 'USING', 'WHILE'}

    def __init__(self, pgcompleter):
        super(self.__class__, self).__init__()
        self.pgcompleter = pgcompleter

    def get_completions(self, document, complete_event, arg_names=()):

        # plpgsql is a superset of sql so let pgcompleter do the heavy lifting
        sql_comps = self.pgcompleter.get_completions(
            document, complete_event, nonsql_completion=False)

        word_before_cursor = document.get_word_before_cursor(WORD=True)

        # Get additional completions suggesting variable names
        local_vars = chain(arg_names, function_variable_names(document.text))
        var_comps = _find_matches(word_before_cursor, local_vars,
                                  case_sensitive=True)

        # Get additional completions suggesting plpgsql keywords
        kwd_comps = _find_matches(word_before_cursor, self.keywords,
                                  case_sensitive=False)

        return combine_completions(sql_comps, var_comps, kwd_comps)


def _find_matches(text, collection, case_sensitive=True):
    # todo: unify w/ pgccmpleter.find_matches?
    if case_sensitive:
        for item in collection:
            if item.startswith(text):
                yield Completion(item, -len(text))
    else:
        text = text.upper()
        for item in collection:
            if item.upper().startswith(text):
                yield Completion(item, -len(text))


def combine_completions(*args):
    """Combine lists of Completions into a single sorted list"""
    return sorted(chain(*args), key=lambda comp: comp.text)
