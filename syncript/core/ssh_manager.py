"""
SSH connection manager with auto-reconnect and keep-alive
"""
from typing import Optional
import ipaddress
import socket
from urllib.parse import unquote, urlparse
import paramiko
from .. import config as _cfg
from ..utils.logging import log
from ..utils.retry import retried


_SOCKS5_REPLY_CODES = {
    0x01: "general SOCKS server failure",
    0x02: "connection not allowed by ruleset",
    0x03: "network unreachable",
    0x04: "host unreachable",
    0x05: "connection refused by destination host",
    0x06: "TTL expired",
    0x07: "command not supported",
    0x08: "address type not supported",
}


def _read_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise RuntimeError("SOCKS proxy closed connection unexpectedly")
        data += chunk
    return data


def _parse_socks_proxy_url(proxy_url: str) -> tuple[str, int, Optional[str], Optional[str]]:
    parsed = urlparse(proxy_url)
    if parsed.scheme.lower() != "socks5":
        raise ValueError("only socks5:// URLs are supported")
    if not parsed.hostname or parsed.port is None:
        raise ValueError("proxy URL must include host and port, e.g. socks5://host:1080")
    username = unquote(parsed.username) if parsed.username is not None else None
    password = unquote(parsed.password) if parsed.password is not None else None
    if username and len(username.encode("utf-8")) > 255:
        raise ValueError("SOCKS proxy username is too long")
    if password and len(password.encode("utf-8")) > 255:
        raise ValueError("SOCKS proxy password is too long")
    return parsed.hostname, parsed.port, username, password


def _open_socks5_tunnel(
    proxy_url: str,
    target_host: str,
    target_port: int,
    timeout: int = 20,
) -> socket.socket:
    proxy_host, proxy_port, username, password = _parse_socks_proxy_url(proxy_url)
    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    sock.settimeout(timeout)
    try:
        methods = [0x00]
        if username is not None:
            methods.append(0x02)
        sock.sendall(bytes([0x05, len(methods), *methods]))
        version, method = _read_exact(sock, 2)
        if version != 0x05:
            raise RuntimeError("invalid SOCKS5 proxy response version")
        if method == 0xFF:
            raise RuntimeError("SOCKS proxy rejected all authentication methods")
        if method == 0x02:
            uname_b = (username or "").encode("utf-8")
            pass_b = (password or "").encode("utf-8")
            auth_req = bytes([0x01, len(uname_b)]) + uname_b + bytes([len(pass_b)]) + pass_b
            sock.sendall(auth_req)
            auth_ver, auth_status = _read_exact(sock, 2)
            if auth_ver != 0x01 or auth_status != 0x00:
                raise RuntimeError("SOCKS proxy authentication failed")
        elif method != 0x00:
            raise RuntimeError(f"SOCKS proxy selected unsupported auth method: {method}")

        try:
            ip = ipaddress.ip_address(target_host)
            if isinstance(ip, ipaddress.IPv4Address):
                atyp = bytes([0x01])
            else:
                atyp = bytes([0x04])
            addr = ip.packed
        except ValueError:
            host_b = target_host.encode("idna")
            if len(host_b) > 255:
                raise RuntimeError("target host name is too long for SOCKS5")
            atyp = bytes([0x03, len(host_b)])
            addr = host_b
        port_b = target_port.to_bytes(2, "big")

        sock.sendall(bytes([0x05, 0x01, 0x00]) + atyp + addr + port_b)

        header = _read_exact(sock, 4)
        ver, rep, _rsv, atyp_reply = header
        if ver != 0x05:
            raise RuntimeError("invalid SOCKS5 connect reply version")
        if rep != 0x00:
            reason = _SOCKS5_REPLY_CODES.get(rep, f"unknown error code {rep}")
            raise RuntimeError(f"SOCKS proxy connect failed: {reason}")

        if atyp_reply == 0x01:
            _read_exact(sock, 4)
        elif atyp_reply == 0x04:
            _read_exact(sock, 16)
        elif atyp_reply == 0x03:
            dom_len = _read_exact(sock, 1)[0]
            _read_exact(sock, dom_len)
        else:
            raise RuntimeError("invalid SOCKS5 connect reply address type")
        _read_exact(sock, 2)
        return sock
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        raise


class SSHManager:
    """
    Wraps paramiko SSHClient + SFTPClient.
    Automatically reconnects on channel errors.
    Sends SSH keep-alives to reduce mid-transfer drops.
    """

    def __init__(self):
        self._ssh: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None

    # ── connection ─────────────────────────────────────────────────────────

    def connect(self):
        if self._ssh:
            try:
                self._ssh.get_transport().send_ignore()  # test if alive
                return
            except Exception:
                self._close_quietly()

        log(f"[SSH] connecting to {_cfg.SSH_USER}@{_cfg.SSH_HOST}:{_cfg.SSH_PORT} …")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kw: dict = dict(hostname=_cfg.SSH_HOST, port=_cfg.SSH_PORT, username=_cfg.SSH_USER,
                        timeout=20, banner_timeout=30, auth_timeout=30)
        if _cfg.SSH_KEY_PATH:
            kw["key_filename"] = _cfg.SSH_KEY_PATH
        if _cfg.SSH_PASSWORD:
            kw["password"] = _cfg.SSH_PASSWORD
        proxy_sock: Optional[socket.socket] = None
        if _cfg.SOCKS_PROXY:
            log(f"[SSH] using SOCKS proxy {_cfg.SOCKS_PROXY}")
            try:
                proxy_sock = _open_socks5_tunnel(
                    _cfg.SOCKS_PROXY,
                    _cfg.SSH_HOST,
                    _cfg.SSH_PORT,
                    timeout=20,
                )
                kw["sock"] = proxy_sock
            except Exception as exc:
                raise RuntimeError(
                    f"failed to connect via SOCKS proxy '{_cfg.SOCKS_PROXY}': {exc}"
                ) from exc

        try:
            client.connect(**kw)
        except Exception:
            if proxy_sock is not None:
                try:
                    proxy_sock.close()
                except Exception:
                    pass
            raise

        # Keep-alive: send a NOP every 30s
        transport = client.get_transport()
        transport.set_keepalive(30)

        self._ssh = client
        self._sftp = client.open_sftp()
        log("[SSH] connected ✓")

    def _close_quietly(self):
        try:
            if self._sftp:
                self._sftp.close()
        except Exception:
            pass
        try:
            if self._ssh:
                self._ssh.close()
        except Exception:
            pass
        self._ssh = None
        self._sftp = None

    def disconnect(self):
        self._close_quietly()
        log("[SSH] disconnected.")

    def ensure_connected(self):
        """Call before any remote operation."""
        try:
            if self._ssh and self._ssh.get_transport().is_active():
                return
        except Exception:
            pass
        self.connect()

    # ── raw exec ────────────────────────────────────────────────────────────

    @retried
    def exec(self, cmd: str, timeout: int = 30) -> tuple[str, str]:
        """Run a command; return (stdout, stderr). Raises on non-zero exit."""
        self.ensure_connected()
        _, stdout, stderr = self._ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            raise RuntimeError(f"remote command exited {rc}: {cmd!r}\nstderr: {err.strip()}")
        return out, err

    def exec_once(self, cmd: str, timeout: int = 30) -> tuple[str, str]:
        """Run a command exactly once (no retry). Use for commands that must not be duplicated."""
        self.ensure_connected()
        _, stdout, stderr = self._ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            raise RuntimeError(f"remote command exited {rc}: {cmd!r}\nstderr: {err.strip()}")
        return out, err

    def exec_nowait(self, cmd: str):
        """Fire-and-forget: don't wait for exit status (for tmux / bg jobs)."""
        self.ensure_connected()
        self._ssh.exec_command(cmd)

    # ── sftp ops ────────────────────────────────────────────────────────────

    @retried
    def sftp_put(self, local: str, remote: str):
        self.ensure_connected()
        self._sftp.put(local, remote)

    @retried
    def sftp_get(self, remote: str, local: str):
        self.ensure_connected()
        self._sftp.get(remote, local)

    @retried
    def sftp_stat(self, remote: str):
        self.ensure_connected()
        return self._sftp.stat(remote)

    @retried
    def sftp_remove(self, remote: str):
        self.ensure_connected()
        self._sftp.remove(remote)

    def sftp_exists(self, remote: str) -> bool:
        try:
            self.sftp_stat(remote)
            return True
        except (FileNotFoundError, IOError):
            return False

    @retried
    def sftp_read_text(self, remote: str) -> str:
        self.ensure_connected()
        with self._sftp.open(remote, "r") as f:
            return f.read().decode("utf-8", errors="replace")
