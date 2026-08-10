"""
Pruebas del soporte de autenticación con llave privada .pem (opción B, AWS EC2):
carga de llaves PEM (RSA/Ed25519), passphrase, rechazo de PEM inválido y el guard
que limita la llave al protocolo SFTP.
"""
import io

import pytest

paramiko = pytest.importorskip("paramiko")

from fastapi import HTTPException

import dev_server


def _rsa_pem(passphrase: str | None = None) -> str:
    key = paramiko.RSAKey.generate(2048)
    buf = io.StringIO()
    key.write_private_key(buf, password=passphrase)
    return buf.getvalue()


def test_load_rsa_pem():
    key = dev_server._load_private_key(_rsa_pem())
    assert key.get_bits() == 2048


def test_load_rsa_pem_encrypted_with_passphrase():
    pem = _rsa_pem(passphrase="s3creta")
    key = dev_server._load_private_key(pem, "s3creta")
    assert key.get_bits() == 2048


def test_load_rsa_pem_encrypted_without_passphrase_falla_claro():
    pem = _rsa_pem(passphrase="s3creta")
    with pytest.raises(Exception, match="passphrase"):
        dev_server._load_private_key(pem)


def test_load_pem_invalido_falla_claro():
    with pytest.raises(Exception, match="No se pudo leer la llave"):
        dev_server._load_private_key("esto no es una llave PEM")


def test_cleanup_conn_pem_solo_sftp():
    server = {"host": "h", "port": 21, "protocol": "ftp", "username": "u"}
    creds = {"password": "", "privateKey": "-----BEGIN...", "passphrase": ""}
    with pytest.raises(HTTPException) as e:
        dev_server._cleanup_conn(server, creds)
    assert e.value.status_code == 400
    assert "SFTP" in e.value.detail


def test_cleanup_conn_pem_sftp_ok():
    server = {"host": "h", "port": 22, "protocol": "sftp", "username": "u"}
    creds = {"password": "", "privateKey": "-----BEGIN...", "passphrase": "x"}
    conn = dev_server._cleanup_conn(server, creds)
    assert conn.privateKey == "-----BEGIN..."
    assert conn.passphrase == "x"


def test_body_creds_extrae_campos():
    body = dev_server.RemoteListBody(server_id="s", password="p", privateKey="k", passphrase="f")
    assert dev_server._body_creds(body) == {"password": "p", "privateKey": "k", "passphrase": "f"}
