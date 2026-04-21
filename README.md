# **LLM Assistant Prefix Proxy**
A lightweight FastAPI-based proxy designed to sit between **SillyTavern** and any **OpenAI-compatible LLM backend** (e.g., Llama.cpp), whose chat endpoints support assistant prefills (e.g., https://docs.litellm.ai/docs/completion/prefix).

## **The Problem**
When you "Continue" in SillyTavern in Chat Completion mode, it sends the payload with the last message being the assistant's if you "Continue", with `Continue prefill` enabled in `AI Response Configuration` (if this is not enabled, a special system message is appended at the end instead). However, in the message there is no `"prefix": true` field set, which some APIs may require.

Additionally, there currently exists a bug in llama.cpp:
- [llama-server returns template-injected <think> tokens as model output in assistant prefill responses (Qwen 3.5) #21511](https://github.com/ggml-org/llama.cpp/issues/21511)
wherein *think* blocks will be printed first with assistant prefix. You can cull these think blocks by setting `assistant_prefill_cull_thinkblock_patterns` in the [configuration](./conf/run_proxy.yaml) appropriately. (Note: this only works for streaming responses, and only if the entire think block is contained within a single streamed chunk.)

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

# **Usage**
1. **Start the Proxy:**
```bash
uv run -m openaiproxyserverforst.proxy
```

Configuration: [./conf/run_proxy.yaml](./conf/run_proxy.yaml).

For debugging, append to command: `log.console_log_level=DEBUG`

2. **Configure via Web UI:**
  A Gradio interface to configure various options in real time is also started simultaneously.

3. In SillyTavern, set API type to `Chat Completion`, and set `Custom Endpoint` to `"http://{proxy_host}:{proxy_port}"` or `"http://{proxy_host}:{proxy_port}/v1"` (or the endpoint of this proxy server that will be printed on screen upon server start).
Within a chat session, when you want to modify the last response of the assistant (or your character), trim its response at the desired point, then click `Continue`.

Note: `AI Response Configuration > Continue Postfix` should be set to `None` to avoid formatting issues.

## **Systemd Installation (Linux)**
To run the proxy as a background service that starts automatically on boot:

1.  **Identify Paths:**
    *   Find the absolute path to your project (e.g., `/home/user/OpenAIProxyServerForST`).
    *   Find the path to the `uv` executable (`which uv`).

2.  **Create Custom Config (Optional):**
    If you want to use a specific backend or port for your server, it's recommended to create a local configuration file in `conf_mine/` (this directory is intended for platform-specific configs and should be kept out of source control).
    Example: `conf_mine/run_proxy_local_llamacpp.yaml`.

3.  **Create Service File:**
    Create a file named `/etc/systemd/system/openai-proxy-4st.service` (requires `sudo`):
    ```ini
    [Unit]
    Description=OpenAI Proxy Server for SillyTavern
    After=network.target

    [Service]
    # Replace with your Linux username
    User=your_username
    # Replace with absolute path to the project
    WorkingDirectory=/path/to/OpenAIProxyServerForST
    # Replace with absolute path to 'uv' and your desired config
    # Example using custom config: ./conf_mine/run_proxy_local_llamacpp.yaml
    ExecStart=/path/to/uv run -m openaiproxyserverforst.proxy --config-dir conf_mine --config-name run_proxy_local_llamacpp
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    ```
    Try running the command in `ExecStart` as a normal user and see if it runs. Also, ensure that an absolute path to uv is provided.

4.  **Enable and Start:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable openai-proxy-4st
    sudo systemctl start openai-proxy-4st
    ```

5.  **Manage Service:**
    ```bash
    # Check status
    sudo systemctl status openai-proxy-4st
    # View logs
    journalctl -u openai-proxy-4st -f
    ```

## **Development & Testing**
This project uses `pytest` for unit testing. 

### Running Tests
To run the entire test suite:
```bash
uv run pytest
```

To run a specific test file:
```bash
uv run pytest tests/test_prefix_injection.py -v
uv run pytest tests/test_stream_culling.py -v
```

The tests cover:
- **Prefix Injection**: Verifying that `"prefix": true` is added correctly to chat completion requests.
- **Stream Culling**: Ensuring think blocks are removed only from the first non-empty chunk of an SSE stream.
- **Unicode Handling**: Confirming that non-ASCII characters (like Korean) are processed without corruption and that `Content-Length` is calculated correctly in bytes.
