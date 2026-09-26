from VexBridge import relay_client
from VexBridge import relay_worker


def main() -> None:
    worker_private = relay_worker.X25519PrivateKey.generate()
    worker_public = relay_worker.public_b64(worker_private)
    node = "interop-node"
    cmd_id = "interop-command"
    envelope, client_shared = relay_client.encrypt_command(
        node,
        worker_public,
        "ping",
        {"deviceId": "interop"},
        ttl_seconds=60,
        cmd_id=cmd_id,
    )
    payload, worker_shared = relay_worker.decrypt_command(worker_private, envelope, node)
    assert payload["tool"] == "ping"
    assert payload["arguments"] == {"deviceId": "interop"}
    assert worker_shared == client_shared

    bodies = relay_worker.encrypted_result(
        worker_shared,
        node,
        cmd_id,
        {"ok": True, "structuredContent": {"pong": True, "host": "interop"}},
    )
    envelopes = []
    for body in bodies:
        parsed = relay_client.parse_result(body)
        assert parsed is not None
        envelopes.append(parsed)
    result = relay_client.decrypt_result_envelopes(node, cmd_id, client_shared, envelopes)
    assert result["result"]["ok"] is True
    assert result["result"]["structuredContent"]["pong"] is True
    print("VEXBRIDGE_RELAY_INTEROP=PASS")


if __name__ == "__main__":
    main()
