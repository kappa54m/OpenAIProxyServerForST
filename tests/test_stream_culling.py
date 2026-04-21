"""
TESTS: Streaming Response Culling
These tests verify that the proxy correctly removes specified "think block" patterns 
from the first non-empty chunk of an SSE stream.

LIMITATION:
Culling only works if the entire think block pattern is contained within 
the first non-empty chunk (where choices[0].delta.content is not null). 
If a think block is split across multiple chunks, it will not be culled.
"""

import pytest
import json

def format_sse(content_value):
    """Helper to format a delta content as an SSE data line (None becomes JSON null)."""
    data = {
        "choices": [{
            "delta": {"content": content_value}
        }]
    }
    return f"data: {json.dumps(data)}\n\n".encode("utf-8")

@pytest.mark.asyncio
async def test_culls_thinkblock_in_first_chunk(client, httpx_mock):
    """Verify culling when the think block is in the very first chunk of the stream."""
    from openaiproxyserverforst.proxy import global_config
    pattern = "<think>\n\n</think>\n\n"
    global_config["assistant_prefill_cull_thinkblock_patterns"] = [pattern]
    
    sse_chunks = [
        format_sse(f"{pattern}Hello"), # 1st chunk contains thinkblock
        format_sse(" world"),
        b"data: [DONE]\n\n"
    ]

    httpx_mock.add_response(
        url="http://mock-backend.local/v1/chat/completions",
        content=b"".join(sse_chunks),
        headers={"Content-Type": "text/event-stream"}
    )

    payload = {"messages": [{"role": "assistant", "content": "..."}], "stream": True}
    response = await client.post("/v1/chat/completions", json=payload)
    
    lines = [line async for line in response.aiter_lines() if line.startswith("data: ")]
    chunk1_data = json.loads(lines[0][len("data: "):])
    assert chunk1_data["choices"][0]["delta"]["content"] == "Hello"

@pytest.mark.asyncio
async def test_culls_after_multiple_null_chunks(client, httpx_mock):
    """Verify culling works after skipping multiple chunks where content is null."""
    from openaiproxyserverforst.proxy import global_config
    pattern = "<think>\n\n</think>\n\n"
    global_config["assistant_prefill_cull_thinkblock_patterns"] = [pattern]
    
    sse_chunks = [
        format_sse(None), # 1. null
        format_sse(None), # 2. null
        format_sse(f"{pattern}Found it"), # 3. First non-null
        b"data: [DONE]\n\n"
    ]

    httpx_mock.add_response(
        url="http://mock-backend.local/v1/chat/completions",
        content=b"".join(sse_chunks),
        headers={"Content-Type": "text/event-stream"}
    )

    payload = {"messages": [{"role": "assistant", "content": "..."}], "stream": True}
    response = await client.post("/v1/chat/completions", json=payload)
    
    lines = [line async for line in response.aiter_lines() if line.startswith("data: ")]
    
    # The third chunk (index 2) is the first non-null one, so it should be culled
    chunk3_data = json.loads(lines[2][len("data: "):])
    assert chunk3_data["choices"][0]["delta"]["content"] == "Found it"

@pytest.mark.asyncio
async def test_does_not_cull_thinkblock_after_first_nonempty_chunk(client, httpx_mock):
    """Verify that a thinkblock appearing in the SECOND non-empty chunk is NOT culled."""
    from openaiproxyserverforst.proxy import global_config
    pattern = "<think>\n\n</think>\n\n"
    global_config["assistant_prefill_cull_thinkblock_patterns"] = [pattern]
    
    sse_chunks = [
        format_sse("Initial text"),        # 1. First non-empty
        format_sse(f"{pattern}Late text"), # 2. Second non-empty containing thinkblock
        b"data: [DONE]\n\n"
    ]

    httpx_mock.add_response(
        url="http://mock-backend.local/v1/chat/completions",
        content=b"".join(sse_chunks),
        headers={"Content-Type": "text/event-stream"}
    )

    payload = {"messages": [{"role": "assistant", "content": "..."}], "stream": True}
    response = await client.post("/v1/chat/completions", json=payload)
    
    lines = [line async for line in response.aiter_lines() if line.startswith("data: ")]
    
    # The second chunk (index 1) should RETAIN the thinkblock because it wasn't the first
    chunk2_data = json.loads(lines[1][len("data: "):])
    assert chunk2_data["choices"][0]["delta"]["content"] == f"{pattern}Late text"

@pytest.mark.asyncio
async def test_culls_gemma4_style_thinkblock(client, httpx_mock):
    """Verify culling of the specific Gemma 4 thought channel pattern."""
    from openaiproxyserverforst.proxy import global_config
    pattern = "<|channel>thought\n<channel|>"
    global_config["assistant_prefill_cull_thinkblock_patterns"] = [pattern]
    
    sse_chunks = [
        format_sse(f"{pattern}Gemma 4 response"),
        b"data: [DONE]\n\n"
    ]

    httpx_mock.add_response(
        url="http://mock-backend.local/v1/chat/completions",
        content=b"".join(sse_chunks),
        headers={"Content-Type": "text/event-stream"}
    )

    payload = {"messages": [{"role": "assistant", "content": "..."}], "stream": True}
    response = await client.post("/v1/chat/completions", json=payload)
    
    lines = [line async for line in response.aiter_lines() if line.startswith("data: ")]
    chunk1_data = json.loads(lines[0][len("data: "):])
    assert chunk1_data["choices"][0]["delta"]["content"] == "Gemma 4 response"
