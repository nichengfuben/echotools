from __future__ import annotations

"""SSH terminal session -- uses paramiko (optional dependency)."""

import asyncio
import io
import logging
import time
from typing import Any, Dict, Optional

from .session import TerminalCallback, TerminalSession

logger = logging.getLogger(__name__)


class SSHTerminal(TerminalSession):
    """Terminal session backed by an SSH connection via *paramiko*.

    *paramiko* is imported lazily so that the rest of the terminal module
    remains usable even when it is not installed.

    Args:
        session_id: Unique session identifier.
        host:       Remote hostname or IP address.
        port:       SSH port (default 22).
        username:   SSH username.
        password:   Password for authentication (optional).
        key_data:   Private key content as a string (optional).
        callback:   Callback handlers for output/error/exit events.
    """

    def __init__(
        self,
        session_id: str,
        host: str,
        port: int = 22,
        username: str = "",
        password: Optional[str] = None,
        key_data: Optional[str] = None,
        callback: Optional[TerminalCallback] = None,
    ) -> None:
        super().__init__(session_id=session_id, kind="ssh", callback=callback)
        self._host: str = host
        self._port: int = port
        self._username: str = username
        self._password: Optional[str] = password
        self._key_data: Optional[str] = key_data

        self._ssh_client: Any = None  # paramiko.SSHClient
        self._ssh_channel: Any = None  # paramiko.Channel

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def start(self, cols: int = 80, rows: int = 24) -> bool:
        """Open an SSH connection and start an interactive shell."""
        self.cols = cols
        self.rows = rows

        try:
            import paramiko
        except ImportError:
            await self._fire_error(
                "paramiko is not installed. "
                "Install it with: pip install paramiko>=3.0.0"
            )
            return False

        try:
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs: Dict[str, Any] = {
                "hostname": self._host,
                "port": self._port,
                "username": self._username,
                "timeout": 15,
            }

            # Authentication priority: key_data > password > system keys
            if self._key_data:
                pkey = self._try_parse_key(paramiko, self._key_data)
                if pkey is None:
                    await self._fire_error(
                        "Failed to parse private key. "
                        "Supported formats: RSA, Ed25519, ECDSA."
                    )
                    return False
                connect_kwargs["pkey"] = pkey
            elif self._password:
                connect_kwargs["password"] = self._password
            else:
                connect_kwargs["look_for_keys"] = True
                connect_kwargs["allow_agent"] = True

            # Connect in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._ssh_client.connect(**connect_kwargs)
            )

            # Open an interactive shell channel
            transport = self._ssh_client.get_transport()
            if transport is None:
                await self._fire_error("SSH transport is unavailable")
                return False

            self._ssh_channel = transport.open_session()
            self._ssh_channel.get_pty(
                term="xterm-256color", width=cols, height=rows
            )
            self._ssh_channel.invoke_shell()
            self.alive = True

            self._reader_task = loop.create_task(self._read_ssh())
            return True

        except Exception as exc:
            await self._fire_error(f"SSH connection failed: {exc}")
            return False

    async def write(self, data: str) -> None:
        """Send input data over the SSH channel."""
        if self._ssh_channel is None:
            return
        try:
            encoded = data.encode("utf-8")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._ssh_channel.send, encoded)
        except Exception:
            logger.debug("SSH write failed (session %s)", self.session_id, exc_info=True)

    async def resize(self, cols: int, rows: int) -> None:
        """Resize the remote PTY."""
        self.cols = cols
        self.rows = rows
        if self._ssh_channel is None:
            return
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._ssh_channel.resize_pty(width=cols, height=rows),
            )
        except Exception:
            logger.debug("SSH resize failed (session %s)", self.session_id, exc_info=True)

    async def close(self) -> None:
        """Close the SSH channel, client, and cancel the reader."""
        self.alive = False

        # 1. Cancel reader
        await self._cancel_reader()

        # 2. Close SSH channel
        if self._ssh_channel is not None:
            try:
                self._ssh_channel.close()
            except Exception:
                pass
            self._ssh_channel = None

        # 3. Close SSH client
        if self._ssh_client is not None:
            try:
                self._ssh_client.close()
            except Exception:
                pass
            self._ssh_client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _try_parse_key(paramiko: Any, key_data: str) -> Any:
        """Attempt to parse a private key in several common formats.

        Tries RSA, Ed25519, and ECDSA in order.  Returns the first
        successfully parsed key, or ``None``.
        """
        for key_class in (
            paramiko.RSAKey,
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
        ):
            try:
                return key_class.from_private_key(io.StringIO(key_data))
            except Exception:
                continue
        return None

    async def _read_ssh(self) -> None:
        """Continuously read from the SSH channel and fire output callbacks."""
        loop = asyncio.get_event_loop()
        try:
            while self.alive and self._ssh_channel is not None:
                data = await loop.run_in_executor(None, self._read_ssh_chunk)
                if data is None:
                    break
                if data:
                    await self._fire_output(data.decode("utf-8", errors="replace"))
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("SSH reader error", exc_info=True)
        finally:
            await self._fire_exit(0)

    def _read_ssh_chunk(self) -> Optional[bytes]:
        """Read a chunk from the SSH channel (blocking, runs in executor).

        Returns ``None`` when the channel is closed or an error occurs.
        Returns an empty ``bytes`` object when no data is available yet
        (the caller should retry).
        """
        if self._ssh_channel is None:
            return None
        try:
            if self._ssh_channel.recv_ready():
                data = self._ssh_channel.recv(4096)
                if not data:
                    return None
                return data
            elif self._ssh_channel.closed or self._ssh_channel.eof_received:
                return None
            else:
                # Small sleep to avoid busy-waiting
                time.sleep(0.05)
                return b""
        except Exception:
            return None
