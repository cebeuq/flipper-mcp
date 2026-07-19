# Contributing

Thanks for your interest in `flipper-mcp`! Contributions are welcome.

## Development setup

```bash
git clone https://github.com/yairhdz24/flipper-mcp.git
cd flipper-mcp
python3 -m venv .venv
./.venv/bin/python -m pip install -e . pytest ruff
```

## Before opening a PR

Run the same checks CI runs:

```bash
./.venv/bin/ruff check flipper_mcp
./.venv/bin/python -m pytest -v
```

- **Tests** in `tests/` must pass. The smoke test asserts the full tool surface is
  registered with usable descriptions — if you add a tool, update the expected count.
- **Lint** with `ruff`; keep changes behavior-neutral where possible.
- If you touch the protobuf schema in `proto/`, regenerate with
  `python scripts/compile_protos.py` and commit the resulting `*_pb2.py`.

## Cross-platform

Keep the Windows raw-USB/WinUSB path (`flipper_mcp/transport/usb.py`) working — it's a
core differentiator. Don't introduce OS-specific assumptions into the shared code;
gate platform-specific logic behind capability checks.

## Safety

Radio-transmit tools affect real RF hardware and spectrum. Any contribution that adds
or changes transmit behavior must keep the safety warnings intact and must not encourage
transmitting on unauthorized frequencies.

## Maintainer

Maintained by [Yair Hernández (@yairhdz24)](https://github.com/yairhdz24). Open an issue
before large changes so we can align on direction.
