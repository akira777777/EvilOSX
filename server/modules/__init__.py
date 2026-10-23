# -*- coding: utf-8 -*-
"""Creates modules using the factory pattern."""
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
from os import path, listdir
from typing import Optional
from zlib import compress

from server.modules.helper import ModuleABC

_module_cache = {}


def load_module(module_name, view, model):
    """Loads the module with error handling and caching.

    :type module_name: str
    :rtype: ModuleABC or None
    """
    if module_name in _module_cache:
        return _module_cache[module_name]

    # Check if source has changed
    current_mtime = _get_source_mtime(module_name)
    if module_name in _last_mtime and _last_mtime[module_name] == current_mtime:
        # Source unchanged, use cached compiled code
        pass
    else:
        _last_mtime[module_name] = current_mtime
        try:
            # Compile bot-side code with error handling
            source_path = path.realpath(path.join(path.dirname(__file__), "bot", module_name + ".py"))
            with open(source_path, "rb") as f:
                source_code = f.read()
            compiled_code = compress(source_code)
            _compiled_cache[module_name] = compiled_code
        except Exception as e:
            view.display_error(f"Failed to compile module '{module_name}': {e}")
            return None

    try:
        # Load server-side module
        module_path = path.realpath(path.join(path.dirname(__file__), "server", module_name + ".py"))
        module = _imp_load.load_source(module_name, module_path)

        if not hasattr(module, 'Module'):
            view.display_error(f"Module '{module_name}' missing Module class")
            return None

        instance = module.Module(view, model)
        _module_cache[module_name] = instance
        return instance
    except Exception as e:
        view.display_error(f"Failed to load module '{module_name}': {e}")
        traceback.print_exc()
        return None

def get_module(module_name):
    """
    :type module_name: str
    :rtype: ModuleABC or None
    :return: The module class if it has been loaded, otherwise None.
    """
    return _module_cache.get(module_name)


def get_names():
    """
    :rtype: list[str]
    :return: A list of all module names which can actually be run on a bot."""
    server_directory = path.realpath(path.join(path.dirname(__file__), "server"))
    bot_directory = path.realpath(path.join(path.dirname(__file__), "bot"))
    # These are handled by the loaders rather than by bot-side module code.
    loader_modules = ["remove_bot", "update_bot"]
    names = []

    for name in listdir(server_directory):
        if not name.endswith(".py") or name in ["__init__.py", "helper.py"]:
            continue

        module_name = name[:-3]

        if module_name in loader_modules or path.isfile(path.join(bot_directory, name)):
            names.append(module_name)

    return sorted(names)


def get_code(module_name):
    """
    :type module_name: str
    :rtype: bytes
    :return: Compressed cached code which can be run on the bot.
    """
    if module_name in _compiled_cache:
        return _compiled_cache[module_name]

    # Fallback to direct compilation (for first load)
    source_path = path.realpath(path.join(path.dirname(__file__), "bot", module_name + ".py"))

    if not path.isfile(source_path):
        raise FileNotFoundError(
            "Module '{}' has no bot-side code ({} is missing).".format(module_name, source_path)
        )

    with open(source_path, "rb") as input_file:
        code = input_file.read()

    _compiled_cache[module_name] = compress(code)
    return _compiled_cache[module_name]
