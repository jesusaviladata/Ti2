from __future__ import annotations

import argparse
import logging
import platform
from pathlib import Path

from .client import AgentClient
from .config import AgentConfig, configured_path
from .identity import IdentityStore
from .journal import ExecutionJournal
from .runner import AgentRunner


def main() -> int:
    parser = argparse.ArgumentParser(prog="data-express-agent")
    parser.add_argument("--config", default=str(configured_path()))
    pairing = parser.add_mutually_exclusive_group()
    pairing.add_argument("--pairing-code")
    pairing.add_argument("--pairing-code-file")
    parser.add_argument("--enroll-only", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    config = AgentConfig.from_file(Path(args.config))
    identity_store = IdentityStore(config.data_dir / "identity.json")
    identity = identity_store.load_or_create()
    client = AgentClient(config, identity)
    pairing_code = args.pairing_code
    pairing_path = Path(args.pairing_code_file) if args.pairing_code_file else None
    if pairing_path and pairing_path.exists():
        pairing_code = pairing_path.read_text(encoding="utf-8").strip()
    if not identity.enrolled:
        if not pairing_code:
            parser.error("se requiere un código de vinculación en la primera ejecución")
        client.enroll(
            pairing_code,
            hostname=platform.node(),
            os_version=platform.platform(),
        )
        identity_store.save(identity)
        if pairing_path:
            pairing_path.unlink(missing_ok=True)
    if args.enroll_only:
        client.close()
        return 0

    runner = AgentRunner(
        client,
        ExecutionJournal(config.data_dir / "execution-journal.json"),
    )
    runner.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
