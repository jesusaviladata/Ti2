from __future__ import annotations

import json

from agent.data_express_agent.config import AgentConfig


def test_configuration_accepts_windows_powershell_utf8_bom(tmp_path):
    path = tmp_path / "agent.json"
    document = {
        "serverUrl": "https://ti2.up.railway.app",
        "commandSigningPublicKey": "public-key",
        "commandSigningKeyId": "railway-2026-08-v2",
        "dataDir": str(tmp_path / "data"),
    }
    path.write_text(json.dumps(document), encoding="utf-8-sig")

    config = AgentConfig.from_file(path)

    assert config.server_url == "https://ti2.up.railway.app"
    assert config.agent_version == "0.2.9"
