# AI Agent Guide: OpenAIProxyServerForST

This document provides essential context and instructions for AI agents working on the **OpenAIProxyServerForST** project.

## 🎯 Project Purpose
This project is a specialized middleware proxy designed to sit between **SillyTavern (ST)** and **OpenAI-compatible LLM backends** (e.g., `llama.cpp`). 

### Problem Statement
In SillyTavern, using the "Continue" feature often appends a final system prompt to request a continuation. This can conflict with backends that require a single system prompt or handle "prefilling" differently. While some backends support a `prefix` argument to continue from an assistant message, SillyTavern's default Chat Completion mode doesn't always set this flag correctly for all APIs.

### The Solution
The proxy addresses these issues by:
1.  **Enabling Assistant Prefilling**: Intercepting chat completion requests where the last message is from the `assistant` and injecting `"prefix": true`. This signals the backend to continue the response from that point.
2.  **Fixing Backend Quirks**: Handling issues like the "think block" bug in `llama.cpp` (Issue #21511), where `<think>` tokens might be incorrectly included in prefilled responses. The proxy culls these patterns from the stream.
3.  **Real-time Configuration**: Providing a Gradio-based Admin UI to modify proxy settings (target URL, feature toggles) without restarting the server.

## 🏗️ Architecture Overview
-   **FastAPI**: Core proxy engine handling all incoming HTTP traffic via a catch-all route.
-   **Gradio**: Administrative web interface mounted at `/ui`.
-   **Hydra**: Configuration management (configs located in `conf/`).
-   **httpx**: Asynchronous HTTP client used to forward intercepted requests to the target LLM backend.

### Key Files
-   `src/openaiproxyserverforst/proxy.py`: Main entry point. Contains FastAPI routes, Gradio UI definition, and proxy logic (`proxy_traffic`).
-   `src/openaiproxyserverforst/logging.py`: Custom logging setup using `LoggerFactory`.
-   `conf/run_proxy.yaml`: Primary configuration file for ports, hostnames, and default patterns.
-   `tests/`: Contains the `pytest` suite for verifying core logic (Prefixes, Culling, Unicode).

## 🛠️ Key Workflows

### 1. Request Interception & Modification
The proxy listens on all paths. For `POST` requests to chat completion endpoints (`/v1/chat/completions`):
-   It parses the JSON body.
-   If the final message role is `assistant` and the `use_prefix` toggle is active, it adds `"prefix": true` to that message object.
-   It recalculates the `Content-Length` header before forwarding.

### 2. SSE Streaming & Culling
If `stream: true` is requested:
-   The proxy streams the response from the backend.
-   If `assistant_prefill_cull_thinkblock_patterns` are configured, it monitors the *first non-empty* data chunk.
-   It removes specified prefixes (like `<think>`) from the content of that first chunk to ensure a clean continuation.

### 3. Dynamic State Management
The `global_config` dictionary in `proxy.py` acts as the single source of truth for the proxy's behavior. The Gradio UI updates this state, and the FastAPI routes read from it for every request.

## 🚦 Development Guidelines

### Debugging
-   Set the log level via Hydra: `uv run -m openaiproxyserverforst.proxy log.console_log_level=DEBUG`.
-   Verify intercepted payloads in the logs to ensure correct JSON modification.

### Testing
-   **Streaming Integrity**: Always verify that streaming responses remain valid SSE events after modification.
-   **Header Preservation**: Ensure headers like `Authorization` are passed through to the backend correctly, while `Host` is properly managed to avoid redirection loops.
-   **UI Sync**: Confirm that changes made in the Gradio UI are immediately reflected in the proxy's behavior.

### Security
-   Sensitive credentials (e.g., `ADMIN_UI_PASSWORD`) should be managed via environment variables or a `.env` file, never hardcoded.

## 🧪 Testing Strategy

### Intercepting Outgoing Requests
The proxy creates its own `httpx.AsyncClient()` instances internally to forward traffic. To test this without a real backend, we use `pytest-httpx`.

**How it works:**
-   `pytest-httpx` "monkeypatches" the `httpx` library during tests.
-   When `proxy_traffic` calls `client.send()`, the request is intercepted by the mock engine.
-   The mock engine returns a pre-defined response and captures the **outgoing request object**.
-   In our tests, we use `httpx_mock.get_request()` to inspect this captured object. This allows us to verify that the proxy correctly modified the JSON payload (e.g., injecting `"prefix": true`) before it would have been sent to the real backend.

### Async Test Configuration
We use **Strict Mode** for `pytest-asyncio`. This means:
-   Async fixtures (like `client` in `tests/conftest.py`) must be explicitly declared with `@pytest_asyncio.fixture(scope="function")`.
-   Asynchronous test functions must be marked with `@pytest.mark.asyncio`.
-   This ensures isolated event loops for every test, preventing state leakage and matching the strict requirements of modern async testing.
