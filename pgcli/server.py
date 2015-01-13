import json

from pgcli.main import PGCli, refresh_completions, format_output
from pgcli.pgcompleter import PGCompleter
from prompt_toolkit.document import Document

from pgcli.packages.pgspecial import (CASE_SENSITIVE_COMMANDS,
        NON_CASE_SENSITIVE_COMMANDS, is_expanded_output)

from mock import Mock
from IPython.kernel.zmq.datapub import publish_data
complete_event = Mock() #??


class Server(object):
    def __init__(self):
        self.pgcli = PGCli(never_passwd_prompt=True)

        self.completer = PGCompleter(smart_completion=True)
        self.completer.extend_special_commands(CASE_SENSITIVE_COMMANDS.keys())
        self.completer.extend_special_commands(NON_CASE_SENSITIVE_COMMANDS.keys())

    def get_completions(self, text, cursor_position):
            self.completer.reset_completions()
            refresh_completions(self.pgcli.pgexecute, self.completer)
            return self.completer.get_completions(
                Document(text=text, cursor_position=cursor_position),
                complete_event)


_server = Server()

def init_server(connstr):
    _server.pgcli.connect_uri(connstr)

    ipython = get_ipython()
    if not ipython.find_line_magic('pgcli.magic'):
        ipython.run_line_magic('load_ext', 'pgcli.magic')


def publish_completions(text, cursor_position):
    completions = _server.get_completions(text, cursor_position)
    data = {'completions': [x.__dict__ for x in completions]}
    publish_data(data)


def print_query_results(sql):
    #TODO: refactor from pgcli.main
    res = _server.pgcli.pgexecute.run(sql)
    output = []
    for rows, headers, status in res:
        output.extend(format_output(rows, headers, status))

    print('\n'.join(output))
