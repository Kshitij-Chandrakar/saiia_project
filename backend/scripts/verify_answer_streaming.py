"""Isolated streaming tests; never load live credentials or allow outbound calls.

Run from any CWD. Extra arguments replace the default focused pytest selection.
"""
import asyncio
import ipaddress
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
os.environ.update(PYTHONDONTWRITEBYTECODE='1', ENABLE_SESSION_ANSWER_MODELS='false',
    GRPC_STT_ENABLED='false', GRPC_ANSWER_STREAM_ENABLED='false',
    ASSEMBLYAI_API_KEY='', OPENAI_API_KEY='', GROQ_API_KEY='', GEMINI_API_KEY='', GOOGLE_API_KEY='',
    SUPABASE_SERVICE_ROLE_KEY='', SUPABASE_ANON_KEY='', NO_PROXY='localhost,127.0.0.1,::1')
node_guard = ROOT / 'frontend/tests/fixtures/loopback_only.cjs'
os.environ['NODE_OPTIONS'] = '--require "' + node_guard.as_posix() + '"'

def allowed(host):
    if host in (None, '', 'localhost'):
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise AssertionError('External network forbidden in isolated tests')

resolve = socket.getaddrinfo
def guarded(host, *args, **kwargs):
    allowed(host)
    return resolve(host, *args, **kwargs)
socket.getaddrinfo = guarded
connect = socket.socket.connect
def local_connect(self, address):
    allowed(address[0])
    return connect(self, address)
socket.socket.connect = local_connect
create = asyncio.BaseEventLoop.create_connection
async def local_connection(self, protocol_factory, host=None, port=None, **kwargs):
    allowed(host)
    return await create(self, protocol_factory, host, port, **kwargs)
asyncio.BaseEventLoop.create_connection = local_connection

if __name__ == '__main__':
    os.chdir(ROOT / 'backend')
    sys.path.insert(0, str(ROOT / 'backend'))
    import pytest
    files = ['test_answer_stream_phase2', 'test_answer_stream_phase3', 'test_answer_stream_characterization',
        'test_session_generation', 'test_answer_model_foundation', 'test_answer_streaming', 'test_grpc_answers',
        'test_grpc_cloud_context', 'test_grpc_auto', 'test_grpc_manual', 'test_grpc_combined', 'test_grpc_realtime',
        'test_grpc_system_audio', 'test_grpc_computer_lifecycle', 'test_grpc_health']
    sys.exit(pytest.main(['-q', *(sys.argv[1:] or ['tests/' + name + '.py' for name in files]),
        '-p', 'no:cacheprovider', '--maxfail=3']))
