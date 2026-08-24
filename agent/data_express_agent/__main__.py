from __future__ import annotations

import argparse
import logging
import platform
from pathlib import Path

from .bootstrap import AgentBootstrap, PairingCodeFile
from .client import AgentClient, AgentClientError
from .config import AgentConfig, configured_path
from .identity import IdentityStore
from .journal import ExecutionJournal
from .runner import AgentRunner
from .file_backup import FileBackupExecutor


def main() -> int:
    parser = argparse.ArgumentParser(prog="data-express-agent")
    parser.add_argument("--config", default=str(configured_path()))
    parser.add_argument("--bootstrap")
    pairing = parser.add_mutually_exclusive_group()
    pairing.add_argument("--pairing-code")
    pairing.add_argument("--pairing-code-file")
    parser.add_argument("--enroll-only", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    bootstrap = (
        AgentBootstrap.from_file(Path(args.bootstrap)) if args.bootstrap else None
    )
    config = (
        AgentConfig.from_bootstrap(bootstrap, Path(args.config))
        if bootstrap is not None
        else AgentConfig.from_file(Path(args.config))
    )
    identity_store = IdentityStore(config.data_dir / "identity.json")
    identity = identity_store.load_or_create()
    client = AgentClient(
        config,
        identity,
        command_trust=bootstrap.command_trust if bootstrap is not None else None,
    )
    pairing_code = args.pairing_code
    pairing_path = Path(args.pairing_code_file) if args.pairing_code_file else None
    pairing_file = PairingCodeFile(pairing_path) if pairing_path else None
    if pairing_path and pairing_path.exists():
        pairing_code = pairing_file.read()
    if not identity.enrolled:
        if not pairing_code:
            parser.error("se requiere un código de vinculación en la primera ejecución")
        try:
            client.enroll(
                pairing_code,
                hostname=platform.node(),
                os_version=platform.platform(),
            )
        except AgentClientError as exc:
            if pairing_file is not None and not exc.recoverable:
                pairing_file.delete()
            raise
        if pairing_file is not None:
            pairing_file.delete()
        identity_store.save(identity)
    if args.enroll_only:
        client.close()
        return 0

    runner = AgentRunner(
        client,
        ExecutionJournal(config.data_dir / "execution-journal.json"),
        file_backup_executor=FileBackupExecutor(
            config.data_dir,
            destination_profiles=config.backup_destinations,
        ),
    )
    runner.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
