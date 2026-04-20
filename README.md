# **LLM Assistant Prefix Proxy**
A lightweight FastAPI-based proxy designed to sit between **SillyTavern** and any **OpenAI-compatible LLM backend** (e.g., Llama.cpp), whose chat endpoints support assistant prefills (e.g., https://docs.litellm.ai/docs/completion/prefix).

## **The Problem**
When you "Continue" in SillyTavern in Chat Completion mode, it sends the payload with the last message being the assistant's if you "Continue", with `Continue prefill` enabled in `AI Response Configuration` (if this is not enabled, a special system message is appended at the end instead). However, in the message there is no `"prefix": true` field set, which some APIs may require

## **The Solution**
This proxy intercepts outgoing chat completion requests and:
1.  Identifies if the final message is from the `assistant`.
2.  Injects a `"prefix": true` flag into that message.
3.  Forwards the request to the real backend while maintaining full **streaming support (SSE)**.
4.  Provides a **web dashboard** to toggle settings without restarting the server.

# **Features**
- **Intelligent Interception:** Automatically handles standard and streaming requests.
- **Gradio Dashboard:** Change the target backend URL and toggle prefix injection in real-time.
  Optionally enable [authentication](https://www.gradio.app/guides/sharing-your-app#authentication) by setting environment variable `ADMIN_UI_ENABLE_AUTH=1`,
  then also setting `ADMIN_UI_USERNAME` and `ADMIN_UI_PASSWORD` to a nonempty value. You can use a `.env` file for this.

Note that this API only intercepts HTTP traffic starting with "/v1", so in SillyTavern you must set `Custom Endpoint (Base URL)` (while `Chat Completion Source` is set to `Custom (OpenAI-compatible)`) to something like "http://127.0.0.1:12434/v1", as opposed to "http://127.0.0.1:12434".

# **Usage**
1. **Start the Proxy:**
```bash
uv run -m openaiproxyserverforst.proxy
```

Configuration: [./conf/run_proxy.yaml](./conf/run_proxy.yaml).

2. **Configure via Web UI:**
  A Gradio interface to configure various options in real time is also started simultaneously. Its address should be the proxy API address + "/ui".

# Caveats
- If your backend is llama.cpp, setting `"prefix": "true"` is actually not necessary to enable assistant prefill.
