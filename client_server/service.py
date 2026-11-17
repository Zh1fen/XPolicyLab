"""Shared policy configuration, model construction and transport selection."""
import argparse
import ast
import asyncio
import importlib
import yaml


def _default_protocol():
    return "ws"


def eval_function_decorator(policy_model_name, name):
    return getattr(importlib.import_module(policy_model_name), name)


def parse_args_and_config(argv=None, *, ws_only=False, default_port=None):
    """Parse CLI args and YAML config, merge overrides"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_path", "--config-path", dest="config_path", type=str, required=True, help="Path to config YAML")
    parser.add_argument("--protocol", choices=(("ws",) if ws_only else ("legacy_tcp", "ws")), help="Policy server protocol")
    parser.add_argument("--host", help="Policy server bind host")
    parser.add_argument("--port", type=int, help="Policy server bind port")
    parser.add_argument("--relay-url", dest="relay_url", help="Relay URL for future relay mode")
    parser.add_argument("--overrides", nargs=argparse.REMAINDER, help="Override config values")
    args = parser.parse_args(argv)

    # Load base config
    with open(args.config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if cfg is None:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError("config must be a YAML mapping")

    # Parse overrides: --key value pairs

    def _parse_val(s: str):
        # safer than eval; supports numbers/bool/None/list/dict when properly quoted
        try:
            return ast.literal_eval(s)
        except Exception:
            return s

    if args.overrides:
        tokens = args.overrides

        # Case A: key=value key=value ...
        if all(("=" in t and not t.startswith("-")) for t in tokens):
            for t in tokens:
                k, v = t.split("=", 1)
                cfg[k] = _parse_val(v)
        else:
            # Case B: --key value --key value ...
            if len(tokens) % 2 != 0:
                raise ValueError(f"--overrides expects key value pairs, got: {tokens}")

            it = iter(tokens)
            for key in it:
                val = next(it)
                cfg[key.lstrip("-")] = _parse_val(val)

    if args.protocol is not None:
        cfg["protocol"] = args.protocol
    else:
        cfg.setdefault("protocol", _default_protocol())
    if args.host is not None:
        cfg["host"] = args.host
    if args.port is not None:
        cfg["port"] = args.port
    if args.relay_url is not None:
        cfg["relay_url"] = args.relay_url

    def _require_non_empty(key: str):
        if key not in cfg:
            raise ValueError(f"{key} must be specified in config or overrides")
        val = cfg[key]
        if val is None:
            raise ValueError(f"{key} must be non-empty")
        if isinstance(val, str) and not val.strip():
            raise ValueError(f"{key} must be non-empty")

    if default_port is not None:
        cfg["host"] = cfg.get("host") or "0.0.0.0"
        if cfg.get("port") is None:
            cfg["port"] = default_port
    _require_non_empty("host")
    _require_non_empty("port")
    if not cfg.get("policy_name"):
        raise ValueError("policy_name must be specified in config")
    cfg["port"] = int(cfg["port"])
    if not 0 <= cfg["port"] <= 65535:
        raise ValueError("port must be between 0 and 65535")
    if ws_only:
        cfg["protocol"] = "ws"
    return cfg


def construct_model(config):
    return eval_function_decorator(f"XPolicyLab.policy.{config['policy_name']}.model", "Model")(config)


def construct_ws_server(config, model=None):
    from client_server.ws.model_server import PolicyServer, PolicyServerConfig
    if model is None:
        model = construct_model(config)
    return PolicyServer(model, PolicyServerConfig(host=config["host"], port=config["port"],
                        ws_ping_interval_s=config.get("ws_ping_interval_s", 20.0),
                        ws_ping_timeout_s=config.get("ws_ping_timeout_s", 20.0)))


def serve(config):
    protocol = config.get("protocol", "ws")
    if protocol not in {"ws", "legacy_tcp"}:
        raise ValueError(f"unsupported policy server protocol: {protocol}")
    model = construct_model(config)
    if protocol == "ws":
        try:
            asyncio.run(construct_ws_server(config, model).serve_forever())
        except KeyboardInterrupt:
            pass
    else:
        from client_server.tcp.model_server import ModelServer
        server = ModelServer(model, host=config["host"], port=config["port"])
        try:
            server.start()
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
