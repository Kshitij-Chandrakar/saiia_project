"""Regenerate bindings from any working directory with the pinned grpcio-tools."""
from pathlib import Path
from grpc_tools import protoc


def main():
    backend = Path(__file__).resolve().parents[1]
    output = backend / "app" / "grpc_generated"
    result = protoc.main([
        "grpc_tools.protoc", f"-I{backend / 'protos'}",
        f"--python_out={output}", f"--grpc_python_out={output}",
        str(backend / "protos" / "interview_realtime.proto"),
    ])
    if result:
        raise SystemExit(result)
    # protoc emits a top-level sibling import; use the repository package instead.
    binding = output / "interview_realtime_pb2_grpc.py"
    binding.write_text(binding.read_text().replace(
        "import interview_realtime_pb2 as", "from . import interview_realtime_pb2 as"
    ))


if __name__ == "__main__":
    main()
