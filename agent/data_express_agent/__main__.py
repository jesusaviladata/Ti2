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
    parser.add_argument("--pairing-code")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    config = AgentConfig.from_file(Path(args.config))
    identity_store = IdentityStore(config.data_dir / "identity.json")
    identity = identity_store.load_or_create()
    client = AgentClient(config, identity)
    if not identity.enrolled:
        if not args.pairing_code:
            parser.error("--pairing-code es obligatorio en la primera vinculación")
        client.enroll(
            args.pairing_code,
            hostname=platform.node(),
            os_version=platform.platform(),
        )
        identity_store.save(identity)

    runner = AgentRunner(
        client,
        ExecutionJournal(config.data_dir / "execution-journal.json"),
    )
    runner.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
