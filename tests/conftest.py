import pytest
import pytest_asyncio
import logging
import openaiproxyserverforst.proxy as proxy
from httpx import ASGITransport, AsyncClient

@pytest.fixture(autouse=True)
def setup_logging():
    """Ensures the proxy's logger is initialized so tests don't crash on log calls."""
    if proxy.logger is None:
        proxy.logger = logging.getLogger("test_logger")
        proxy.logger.setLevel(logging.DEBUG)
        if not proxy.logger.handlers:
            handler = logging.StreamHandler()
            proxy.logger.addHandler(handler)

@pytest.fixture(autouse=True)
def reset_config():
    """Resets the global configuration to defaults before every single test."""
    proxy.global_config["target_url"] = "http://mock-backend.local"
    proxy.global_config["use_prefix"] = True
    proxy.global_config["assistant_prefill_cull_thinkblock_patterns"] = []
    return proxy.global_config

# We use @pytest_asyncio.fixture to explicitly register async fixtures 
# when running in 'Strict' mode (required for pytest-asyncio).
@pytest_asyncio.fixture(scope="function")
async def client():
    """Provides an async client to call the FastAPI routes during tests."""
    # ASGITransport allows httpx to call the FastAPI app directly in-process
    transport = ASGITransport(app=proxy.web)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
