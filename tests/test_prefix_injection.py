"""
TESTS: Prefix Injection Logic
These tests verify that the proxy correctly injects '"prefix": true' into the JSON payload 
BEFORE forwarding it to the backend.

HOW IT WORKS: 
Since the proxy creates its own httpx.AsyncClient() internally, we use `httpx_mock` 
to intercept the outgoing request and verify its content. See AGENTS.md for details.
"""

import pytest
import json

@pytest.mark.asyncio
async def test_prefix_injected_on_assistant_last_msg(client, httpx_mock):
    """Verify prefix is added to chat completion requests when the last message is assistant."""
    # 1. Setup the mock backend
    httpx_mock.add_response(
        method="POST",
        url="http://mock-backend.local/v1/chat/completions",
        json={"choices": [{"message": {"content": "Forwarded successfully"}}]}
    )

    # 2. Incoming request from SillyTavern
    payload = {
        "messages": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "How can I help?"}
        ]
    }

    # 3. Send to Proxy
    await client.post("/v1/chat/completions", json=payload)

    # 4. Check what the Proxy sent to the Backend
    backend_request = httpx_mock.get_request()
    sent_payload = json.loads(backend_request.read())
    
    # 5. Assert injection
    assert sent_payload["messages"][-1]["prefix"] is True

@pytest.mark.asyncio
async def test_prefix_not_injected_on_user_last_msg(client, httpx_mock):
    """Verify prefix is NOT added when the last message is from the user."""
    httpx_mock.add_response(url="http://mock-backend.local/v1/chat/completions")

    payload = {
        "messages": [
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Continue this..."}
        ]
    }

    await client.post("/v1/chat/completions", json=payload)
    
    backend_request = httpx_mock.get_request()
    sent_payload = json.loads(backend_request.read())
    
    assert "prefix" not in sent_payload["messages"][-1]

@pytest.mark.asyncio
async def test_prefix_not_injected_on_system_last_msg(client, httpx_mock):
    """Verify prefix is NOT added when the last message is from the user."""
    httpx_mock.add_response(url="http://mock-backend.local/v1/chat/completions")

    payload = {
        "messages": [
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Continue this..."},
            {"role": "system", "content": "[Continue your last message without repeating its original content.]"}
        ]
    }

    await client.post("/v1/chat/completions", json=payload)
    
    backend_request = httpx_mock.get_request()
    sent_payload = json.loads(backend_request.read())
    
    assert "prefix" not in sent_payload["messages"][-1]

@pytest.mark.asyncio
async def test_prefix_not_injected_when_disabled(client, httpx_mock):
    """Verify prefix is NOT added if the user turned off the feature."""
    from openaiproxyserverforst.proxy import global_config
    global_config["use_prefix"] = False
    
    httpx_mock.add_response(url="http://mock-backend.local/v1/chat/completions")

    payload = {
        "messages": [{"role": "assistant", "content": "I am an assistant"}]
    }

    await client.post("/v1/chat/completions", json=payload)
    
    backend_request = httpx_mock.get_request()
    sent_payload = json.loads(backend_request.read())
    
    assert "prefix" not in sent_payload["messages"][-1]

@pytest.mark.asyncio
async def test_prefix_works_on_alternative_chat_endpoint(client, httpx_mock):
    """Verify it also works for the /chat/completions endpoint (without /v1 prefix)."""
    httpx_mock.add_response(url="http://mock-backend.local/chat/completions")

    payload = {
        "messages": [{"role": "assistant", "content": "I am an assistant"}]
    }

    await client.post("/chat/completions", json=payload)
    
    backend_request = httpx_mock.get_request()
    sent_payload = json.loads(backend_request.read())
    assert sent_payload["messages"][-1]["prefix"] is True

@pytest.mark.asyncio
async def test_unicode_handling_and_content_length(client, httpx_mock):
    """
    Verify that non-ASCII characters (Korean) are handled correctly and 
    the Content-Length header is based on bytes, not characters.
    """
    httpx_mock.add_response(url="http://mock-backend.local/v1/chat/completions")

    # A payload with Korean characters
    korean_content = "안녕하세요" # 5 characters, 15 bytes in UTF-8
    payload = {
        "messages": [
            {"role": "user", "content": korean_content},
            {"role": "assistant", "content": "네, 반가워요!"}
        ]
    }
    
    # Send as raw UTF-8 bytes to simulate a real network request
    raw_json_bytes = json.dumps(payload).encode("utf-8")
    await client.post(
        "/v1/chat/completions", 
        content=raw_json_bytes,
        headers={"Content-Type": "application/json"}
    )
    
    backend_request = httpx_mock.get_request()
    
    # 1. Verify Content-Length is the size of the bytes, not character count
    # (The proxy adds '"prefix": true' which adds more bytes)
    sent_body = backend_request.read()
    expected_length = len(sent_body)
    assert int(backend_request.headers["content-length"]) == expected_length
    
    # 2. Verify characters survived the round-trip
    sent_payload = json.loads(sent_body)
    assert sent_payload["messages"][0]["content"] == korean_content
