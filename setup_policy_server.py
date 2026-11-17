"""Public root policy service CLI; shared construction lives in client_server.service."""
from client_server.service import eval_function_decorator, parse_args_and_config, serve as main, _default_protocol

if __name__ == "__main__":
    main(parse_args_and_config())
