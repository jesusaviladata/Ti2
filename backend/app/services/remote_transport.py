from __future__ import annotations

import base64
import ftplib
import hashlib
import io
import posixpath
import socket
import stat
from dataclasses import dataclass
from typing import Any

from app.core.errors import DependencyUnavailableError, DomainError

from remote_cleanup import contains_traversal, is_within_allowlist, normalize_remote


@dataclass(slots=True)
class RemoteCredentials:
    password: str = ""
    private_key: str = ""
    passphrase: str = ""


@dataclass(slots=True)
class RemoteServerConfig:
    protocol: str
    host: str
    port: int
    username: str
    base_path: str
    allowlist: list[str]


def validate_remote_path(path: str, allowlist: list[str]) -> str:
    if contains_traversal(path):
        raise DomainError("REMOTE_PATH_TRAVERSAL", "La ruta contiene '..'", 403)
    normalized = normalize_remote(path)
    if not normalized.startswith("/"):
        raise DomainError(
            "REMOTE_PATH_NOT_ABSOLUTE",
            "La ruta remota debe ser absoluta",
            422,
        )
    if not is_within_allowlist(normalized, allowlist):
        raise DomainError(
            "REMOTE_PATH_NOT_ALLOWED", "La ruta está fuera de la allowlist", 403
        )
    return normalized


def fingerprint_key(key: Any) -> tuple[str, str]:
    digest = hashlib.sha256(key.asbytes()).digest()
    return key.get_name(), "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def probe_ssh_host_key(host: str, port: int) -> tuple[str, str]:
    try:
        import paramiko

        sock = socket.create_connection((host, port), timeout=15)
        try:
            transport = paramiko.Transport(sock)
            transport.start_client(timeout=15)
            key = transport.get_remote_server_key()
            return fingerprint_key(key)
        finally:
            try:
                transport.close()
            except Exception:
                sock.close()
    except Exception as exc:
        raise DependencyUnavailableError("SFTP", str(exc)[:512]) from exc


class RemoteClient:
    def list_one(self, path: str) -> list[dict]:
        raise NotImplementedError

    def move(self, source: str, destination: str) -> None:
        raise NotImplementedError

    def remove(self, path: str) -> None:
        raise NotImplementedError

    def mkdir(self, path: str) -> None:
        raise NotImplementedError

    def rmdir(self, path: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def collect_tree(
        self, roots: list[str], allowlist: list[str], cap: int = 50_000
    ) -> tuple[list[dict], bool]:
        entries: list[dict] = []
        queue = [validate_remote_path(root, allowlist) for root in roots]
        visited: set[str] = set()
        while queue and len(entries) < cap:
            directory = queue.pop(0)
            if directory in visited:
                continue
            visited.add(directory)
            for entry in self.list_one(directory):
                safe = validate_remote_path(entry["path"], allowlist)
                entry["path"] = safe
                entries.append(entry)
                if entry.get("isDir") and not entry.get("isLink"):
                    queue.append(safe)
                if len(entries) >= cap:
                    break
        return entries, bool(queue)


class FTPRemoteClient(RemoteClient):
    def __init__(self, config: RemoteServerConfig, credentials: RemoteCredentials):
        client = ftplib.FTP_TLS() if config.protocol == "ftps" else ftplib.FTP()
        try:
            client.connect(config.host, config.port, timeout=20)
            client.login(config.username, credentials.password)
            if config.protocol == "ftps":
                client.prot_p()
        except Exception as exc:
            try:
                client.close()
            except Exception:
                pass
            raise DependencyUnavailableError(config.protocol.upper(), str(exc)[:512])
        self.client = client

    def list_one(self, path: str) -> list[dict]:
        result: list[dict] = []
        try:
            for name, facts in self.client.mlsd(path):
                if name in {".", ".."}:
                    continue
                item_path = posixpath.join(path.rstrip("/"), name)
                modified = None
                if facts.get("modify"):
                    from datetime import datetime, timezone

                    modified = datetime.strptime(
                        facts["modify"][:14], "%Y%m%d%H%M%S"
                    ).replace(tzinfo=timezone.utc).timestamp()
                result.append(
                    {
                        "name": name,
                        "path": item_path,
                        "sizeBytes": int(facts.get("size", 0) or 0),
                        "modified": modified,
                        "isDir": facts.get("type") == "dir",
                        "isLink": False,
                        "permissions": facts.get("perm"),
                    }
                )
            return result
        except Exception as exc:
            raise DependencyUnavailableError("FTP", str(exc)[:512]) from exc

    def _mkdirs(self, directory: str) -> None:
        current = ""
        for part in [part for part in directory.split("/") if part]:
            current += "/" + part
            try:
                self.client.mkd(current)
            except Exception:
                pass

    def move(self, source: str, destination: str) -> None:
        self._mkdirs(posixpath.dirname(destination))
        self.client.rename(source, destination)

    def remove(self, path: str) -> None:
        self.client.delete(path)

    def mkdir(self, path: str) -> None:
        self._mkdirs(path)

    def rmdir(self, path: str) -> None:
        self.client.rmd(path)

    def close(self) -> None:
        try:
            self.client.quit()
        except Exception:
            self.client.close()


class SFTPRemoteClient(RemoteClient):
    def __init__(self, config: RemoteServerConfig, credentials: RemoteCredentials):
        try:
            import paramiko

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            kwargs: dict[str, Any] = {
                "hostname": config.host,
                "port": config.port,
                "username": config.username,
                "timeout": 20,
                "look_for_keys": False,
                "allow_agent": False,
            }
            if credentials.private_key:
                key = None
                for key_class in (
                    paramiko.RSAKey,
                    paramiko.Ed25519Key,
                    paramiko.ECDSAKey,
                ):
                    try:
                        key = key_class.from_private_key(
                            io.StringIO(credentials.private_key),
                            password=credentials.passphrase or None,
                        )
                        break
                    except Exception:
                        continue
                if key is None:
                    raise ValueError("La llave privada no tiene un formato compatible")
                kwargs["pkey"] = key
            else:
                kwargs["password"] = credentials.password
            # The key is verified before this constructor. Load only that exact key.
            algorithm, fingerprint = probe_ssh_host_key(config.host, config.port)
            key_store = client.get_host_keys()
            transport = paramiko.Transport((config.host, config.port))
            transport.start_client(timeout=15)
            key = transport.get_remote_server_key()
            transport.close()
            if fingerprint_key(key) != (algorithm, fingerprint):
                raise ValueError("La host key cambió durante la conexión")
            key_store.add(config.host, algorithm, key)
            key_store.add(f"[{config.host}]:{config.port}", algorithm, key)
            client.connect(**kwargs)
            self.client = client
            self.sftp = client.open_sftp()
        except DomainError:
            raise
        except Exception as exc:
            raise DependencyUnavailableError("SFTP", str(exc)[:512]) from exc

    def list_one(self, path: str) -> list[dict]:
        result: list[dict] = []
        try:
            resolved = normalize_remote(self.sftp.normalize(path))
            for attr in self.sftp.listdir_attr(resolved):
                item_path = posixpath.join(resolved.rstrip("/"), attr.filename)
                result.append(
                    {
                        "name": attr.filename,
                        "path": item_path,
                        "sizeBytes": int(attr.st_size or 0),
                        "modified": float(attr.st_mtime) if attr.st_mtime else None,
                        "isDir": stat.S_ISDIR(attr.st_mode),
                        "isLink": stat.S_ISLNK(attr.st_mode),
                        "permissions": oct(attr.st_mode & 0o777),
                    }
                )
            return result
        except Exception as exc:
            raise DependencyUnavailableError("SFTP", str(exc)[:512]) from exc

    def _mkdirs(self, directory: str) -> None:
        current = ""
        for part in [part for part in directory.split("/") if part]:
            current += "/" + part
            try:
                self.sftp.stat(current)
            except OSError:
                self.sftp.mkdir(current)

    def move(self, source: str, destination: str) -> None:
        self._mkdirs(posixpath.dirname(destination))
        try:
            self.sftp.posix_rename(source, destination)
        except (AttributeError, OSError):
            self.sftp.rename(source, destination)

    def remove(self, path: str) -> None:
        self.sftp.remove(path)

    def mkdir(self, path: str) -> None:
        self._mkdirs(path)

    def rmdir(self, path: str) -> None:
        self.sftp.rmdir(path)

    def close(self) -> None:
        try:
            self.sftp.close()
        finally:
            self.client.close()


def open_remote_client(
    config: RemoteServerConfig, credentials: RemoteCredentials
) -> RemoteClient:
    if config.protocol in {"ftp", "ftps"}:
        return FTPRemoteClient(config, credentials)
    if config.protocol == "sftp":
        return SFTPRemoteClient(config, credentials)
    raise DomainError("UNSUPPORTED_PROTOCOL", "Protocolo remoto no soportado", 422)
