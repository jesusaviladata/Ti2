from app.services.remote_transport import FTPRemoteClient, RemoteClient, SFTPRemoteClient


def test_all_remote_clients_support_directory_removal():
    assert callable(getattr(RemoteClient, "rmdir", None))
    assert callable(getattr(FTPRemoteClient, "rmdir", None))
    assert callable(getattr(SFTPRemoteClient, "rmdir", None))
