"""
TESTS: Path Forwarding Logic
Verifies that the proxy correctly forwards various common endpoints 
and preserves the request body.
"""

import pytest
import json

@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/completion", "/completions", "/models", "/v1/models"])
async def test_forwards_endpoints_correctly(client, httpx_mock, path):
    """
    Verify that multiple endpoints are forwarded correctly for both 
    GET and POST, and the content is preserved.
    """
    # 1. Setup mock backend for BOTH methods
    # We do this at once so httpx_mock doesn't complain about unrequested mocks
    httpx_mock.add_response(
        method="POST",
        url=f"http://mock-backend.local{path}",
        json={"success": "post"}
    )
    httpx_mock.add_response(
        method="GET",
        url=f"http://mock-backend.local{path}",
        json={"success": "get"}
    )

    # 2. Test POST forwarding
    payload = {"test_key": f"test_value_for_{path}"}
    post_res = await client.post(path, json=payload)
    assert post_res.status_code == 200
    assert post_res.json()["success"] == "post"
    
    # Verify what reached the backend
    post_request = httpx_mock.get_requests()[-1]
    assert str(post_request.url) == f"http://mock-backend.local{path}"
    assert json.loads(post_request.read()) == payload
    assert post_request.method == "POST"

    # 3. Test GET forwarding
    get_res = await client.get(path)
    assert get_res.status_code == 200
    assert get_res.json()["success"] == "get"
    
    # Verify what reached the backend
    get_request = httpx_mock.get_requests()[-1]
    assert str(get_request.url) == f"http://mock-backend.local{path}"
    assert get_request.method == "GET"
