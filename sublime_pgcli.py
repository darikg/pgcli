import sys
import os

#http://sublime-text-unofficial-documentation.readthedocs.org/en/latest/extensibility/plugins.html
#http://stackoverflow.com/questions/9977446/connecting-to-a-remote-ipython-instance
#http://nbviewer.ipython.org/gist/minrk/5672711
#https://www.sublimetext.com/docs/3/api_reference.html
#http://sublime-text-unofficial-documentation.readthedocs.org/en/latest/extensibility/plugins.html

# TODO: Move to plugin settings
#PYTHON_PATH = r'C:\Users\dg\Anaconda3\envs\pgcli2\python.exe'
PYTHON_PATH = r'C:\Users\dg\Anaconda3\envs\pgcli3\pythonw.exe'
CONNECTION_STR = 'postgresql://postgres@localhost/test'
IPYTHON_CMD = 'from IPython.kernel.zmq.kernelapp import main; main()'

# Sublime text 3 ships with its own python interpreter
# Need to tell it where to look for extra packages
# (Specifically IPython and pyzmq)
SUBLIME_IPYTHON_DIR = r'C:\Users\dg\Anaconda3\envs\sublimetext3\lib\site-packages'
if SUBLIME_IPYTHON_DIR and SUBLIME_IPYTHON_DIR not in sys.path:
    sys.path.insert(0, SUBLIME_IPYTHON_DIR)

# By default, popen will start a subprocess with an environment duplicated
# from the sublime text process. This is a problem if we want to run pgcli
# with a different python version then the sublime text python (v3.3)
PGCLI_KERNEL_PATH = r'C:\Users\dg\Anaconda3\envs\pgcli3;' \
                    r'C:\Users\dg\Anaconda3\envs\pgcli2\lib\site-packages;'
_kernel_env = os.environ.copy()
_kernel_env['PYTHONPATH'] = ''
_kernel_env['PATH'] = PGCLI_KERNEL_PATH


import sublime
import sublime_plugin
import logging
import re
import time
from subprocess import Popen, PIPE, STDOUT
from queue import Queue

from IPython.kernel.connect import find_connection_file
from IPython.kernel.blocking.client import BlockingKernelClient
from IPython.kernel.zmq.serialize import unserialize_object

# Initialize logging
_logger = logging.getLogger('pgcli.plugin')
_logger.setLevel(logging.DEBUG) 

if not _logger.handlers:
    ch = logging.StreamHandler(sys.stdout)
    _logger.addHandler(ch)

_logger.debug('starting plugin')
_logger.debug('Current directory: %r', os.getcwd())

_pgcli_client = None

#Queues for passing data between threads
_exec_queue = Queue()  # Commands to be executed on the kernel
_data_queue = Queue()  # Incoming data from the kernel


def plugin_loaded():
    global _pgcli_client
    _pgcli_client = PgcliClient(CONNECTION_STR)

    #Start the main polling loop in a separate thread
    sublime.set_timeout_async(main_polling_loop, 0)


def plugin_unloaded():
    _logger.debug('Terminating kernel')
    if _pgcli_client:
        _pgcli_client.terminate()


class PgcliClient(object):
    def __init__(self, connstr):
        _logger.debug('Opening kernel process')
        self.popen = Popen([PYTHON_PATH, '-c', IPYTHON_CMD],
                        stdout=PIPE, stderr=STDOUT, bufsize=-1, env=_kernel_env)
        _logger.debug('Waiting for kernel start')

        #Currently, we get the json file specifying connection details from
        #scanning stdout
        #todo: supply a path where kernel can write the file
        self.json_file = _get_json_file_from_popen(self.popen)
        _logger.debug('Found json file: %r', self.json_file)

        #Create a new client for communicating with the kernel
        _logger.debug('Connecting client')
        self.client = BlockingKernelClient(connection_file=self.json_file)
        self.client.load_connection_file()
        self.client.start_channels()

        _logger.debug('Initializing pgcli server')
        self.exec('from pgcli.server import *')
        self.exec('init_server("{}")'.format(connstr))

    def exec(self, code):
        self.client.shell_channel.execute(code)

    def terminate(self):
        if self.popen:
            try:
                self.popen.terminate()
            except Exception as err:
                _logger.debug('Error terminating kernel: %r', err)


class PgcliSublimePlugin(sublime_plugin.EventListener):
    def on_query_completions(self, view, prefix, locations):
        """Called by sublime when requesting autocomplete options"""

        text = get_entire_view_text(view)
        cursor_pos = view.sel()[0].begin()

        cmd = 'publish_completions("{}", {})'.format(text, cursor_pos)

        _logger.debug('Sending publish_completions request: %r', cmd)
        _exec_queue.put(cmd)

        _logger.debug('Waiting for completions')
        data = _data_queue.get(block=True, timeout=1)
        completions = data['completions']
        _logger.debug('Found completions: %r', completions)
        _logger.debug(completions)
        #return ['apples', 'ananas']
        return [(x['text'], x['display']) for x in completions]



def main_polling_loop():
    pub = _pgcli_client.client.iopub_channel
    
    while _pgcli_client:

        #Check for outstanding messages from kernel
        for msg in pub.get_msgs():
            typ = msg['msg_type']
            _logger.debug('%r: %r', typ, msg)

            if typ == 'pyerr':
                _logger.debug('\n'.join(msg['content']['traceback']))
                raise IOError()
            elif typ == 'pyout':
                pass
            elif typ == 'stream':
                print(msg['content']['data'])
            elif typ == 'data_message':
                data = unserialize_object(msg['buffers'])
                #I think data is always wrapped in a list?
                data = data[0]
                _data_queue.put(data)

        #Check for outgoing requests to the kernel
        while not _exec_queue.empty():
            command = _exec_queue.get()
            _pgcli_client.exec(command)

        #Wait for running again
        time.sleep(.1)


def _get_json_file_from_popen(popen):
    json_match = None
    while not json_match:
        s = popen.stdout.readline()
        s = s.decode('utf-8')
        _logger.debug(s)

        if 'Error' in s:
            raise IOError()

        json_match = re.search('(\d+\.json)', s)

    return find_connection_file(json_match.group(1))

 
def get_entire_view_text(view):
    return view.substr(sublime.Region(0, view.size()))


class PgcliExecuteCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        """Execute the entire contents of the buffer"""

        sql = get_entire_view_text(self.view)

        _logger.debug('Command: PgcliExecute: %r', sql)

        cmd = 'print_query_results("{}")'.format(sql)
        _exec_queue.put(cmd)


