import json
import logging
from logging import Logger
import os
import sys
from typing import Any, Sequence, Mapping

from omegaconf import DictConfig
import hydra
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import httpx
import gradio as gr
import gradio.themes as gr_themes
import uvicorn
from dotenv import load_dotenv

from .logging import LoggerFactory


logger: Logger = None # pyright: ignore [reportAssignmentType]

os.environ['GRADIO_ANALYTICS_ENABLED'] = "False"

load_dotenv()

# --- STATE MANAGEMENT ---
# Holds our persistent settings in memory.
global_config = {
    "target_url": None,
    "use_prefix": True,
    "assistant_prefill_cull_thinkblock_patterns": [],
}

web = FastAPI()

# --- GRADIO WEB INTERFACE ---
def update_settings(new_url, use_prefix):
    # Strip trailing slashes to prevent double-slash URL errors later
    global_config["target_url"] = new_url.rstrip("/")
    global_config["use_prefix"] = use_prefix
    
    status_msg = (
        f"✅ Success!\n"
        f"• Target URL: {global_config['target_url']}\n"
        f"• Prefix Injection: {'Enabled' if use_prefix else 'Disabled'}"
    )
    return status_msg

def get_current_settings():
    return global_config["target_url"], global_config["use_prefix"]

# Build the UI
with gr.Blocks() as admin_ui:
    gr.Markdown("# 🎛️ Proxy Settings Dashboard")
    gr.Markdown("Configure your LLM backend URL and modify payload interception behavior.")
    
    with gr.Row():
        url_input = gr.Textbox(label="LLM Endpoint URL", value=global_config["target_url"], scale=3)
        prefix_toggle = gr.Checkbox(label="Inject 'prefix: true' on Continues", value=global_config["use_prefix"], scale=1)
    
    with gr.Row():
        save_btn = gr.Button("Save Configuration", variant="primary")
        
    status_output = gr.Textbox(label="Status", interactive=False, lines=3)
    
    # Map the inputs to the function
    save_btn.click(
        fn=update_settings, 
        inputs=[url_input, prefix_toggle], 
        outputs=status_output
    )

    admin_ui.load(
        fn=get_current_settings,
        inputs=[],
        outputs=[url_input, prefix_toggle]
    )


# --- FASTAPI CATCH-ALL PROXY ---
@web.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_traffic(request: Request, path: str):
    target_url = global_config["target_url"]
    destination_url = f"{target_url}/{path}"

    # Extract headers and remove 'host' so the target server doesn't get confused
    headers = dict(request.headers)
    headers.pop("host", None)

    is_chat_completion = path.startswith("v1/chat/completions") or path.startswith("chat/completions")
    
    # Read the raw incoming body
    body = await request.body()

    is_intercepted = False
    is_stream = False
    
    # Intercept and modify POST requests containing JSON (like /v1/chat/completions)
    if request.method == "POST" and "application/json" in headers.get("content-type", ""):
        try:
            payload = json.loads(body)
            # If it's a chat completions request, check for messages
            if is_chat_completion:
                if "messages" in payload and isinstance(payload["messages"], list) and len(payload["messages"]) > 0:
                    last_msg = payload["messages"][-1]
                    
                    # If SillyTavern is Continuing AND the user has the toggle enabled
                    if last_msg.get("role") == "assistant" and global_config["use_prefix"]:
                        last_msg["prefix"] = True
                        is_intercepted = True
                        logger.info("--> [Intercepted] Injected prefix: true into assistant message")
                        logger.debug("Intercepted payload (parsed): %s", payload)
                
            # Check if SillyTavern requested a stream
            is_stream = payload.get("stream", False)
                
            # Repackage the modified JSON
            body = json.dumps(payload).encode("utf-8")
            headers["content-length"] = str(len(body))
        except json.JSONDecodeError as e:
            logger.exception("Failed to parse JSON request: {}".format(body), e)

    # Forward the request using httpx
    client = httpx.AsyncClient(timeout=300.0)
    
    req = client.build_request(
        method=request.method,
        url=destination_url,
        headers=headers,
        content=body,
        params=request.query_params
    )

    parse_stream_output = False
    if is_intercepted:
        if global_config['assistant_prefill_cull_thinkblock_patterns']:
            parse_stream_output = True

    # Handle the response (Streaming vs Standard)
    if is_stream:
        async def stream_generator():
            async with client.stream(req.method, req.url, headers=req.headers, content=req.content) as resp:
                if not parse_stream_output:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
                else:
                    chunk_idx = 0
                    last_chunk_had_empty_msg = True
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            json_str = line[len("data: "):]
                            
                            # Handle the end-of-stream marker
                            if json_str.strip() == "[DONE]":
                                yield b"data: [DONE]\n\n"
                                continue
                                
                            chunk_decode_success = False
                            try:
                                data = json.loads(json_str)
                                chunk_decode_success = True
                            except json.JSONDecodeError as e:
                                logger.exception("Failed to parse chat completion chunk", e)

                            if chunk_decode_success:
                                logger.debug("Decoded chunk: %s", data)
                                is_first_nonempty_chunk = False
                                if last_chunk_had_empty_msg:
                                    if data.get('choices', None):
                                        first_choice = data['choices'][0]
                                        delta = first_choice['delta']
                                        content = delta['content']
                                        if content is not None:
                                            last_chunk_had_empty_msg = False
                                            is_first_nonempty_chunk = True

                                modified_data = modify_chat_completion_chunk(data, is_first_nonempty_chunk=is_first_nonempty_chunk)
                                modified_json_str = json.dumps(modified_data, separators=(',', ':'))
                                new_chunk = f"data: {modified_json_str}\n\n"
                                yield new_chunk.encode("utf-8")
                            else:
                                yield f"{line}\n\n".encode("utf-8")

                            chunk_idx += 1
                        elif line.strip() == "": # Ignore empty lines (we add \n\n manually during yield)
                            continue 
                        else: # Pass through non-data lines (like SSE comments or event type lines) unharmed
                            yield f"{line}\n\n".encode("utf-8")
        return StreamingResponse(stream_generator())
    else:
        # Standard non-streaming response
        resp = await client.send(req)
        # Filter out headers that might mess up the browser/ST parsing
        resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ['content-encoding', 'content-length', 'transfer-encoding', 'connection']}
        return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)


def modify_chat_completion_chunk(cur_chunk_d: dict, is_first_nonempty_chunk: bool) -> dict:
    modified_chunk_d = {**cur_chunk_d}

    if is_first_nonempty_chunk:
        content = cur_chunk_d['choices'][0]['delta']['content']
        for i, thinkblock_str in enumerate(global_config['assistant_prefill_cull_thinkblock_patterns']):
            if content.startswith(thinkblock_str):
                new_content = content[len(thinkblock_str):]
                cur_chunk_d['choices'][0]['delta']['content'] = new_content
                logger.debug(("Culled thinkblock string from first nonempty chunk content;"
                              " modified chunk: %s (thinkblock pattern %d: %s)"), cur_chunk_d, i+1, thinkblock_str)
                break

    return modified_chunk_d


@hydra.main(version_base=None, config_path='../../conf', config_name='run_proxy')
def main(cfg: DictConfig):
    log_cfg = cfg['log']
    lf = LoggerFactory(
        console_logging_level=log_cfg['console_log_level'],
        do_file_logging=log_cfg['do_file_log'],
        file_logging_level=log_cfg['file_log_level'],
        file_logging_dir=log_cfg['file_log_dir'],
        time_zone_str=log_cfg['timezone'])
    global logger
    logger = lf.get_logger(__name__)

    proxy_host = cfg['proxy_host']
    proxy_port = int(cfg['proxy_port'])
    target_url = cfg['openai_api_base']
    admin_ui_host = cfg['admin_ui_host']
    admin_ui_port = int(cfg['admin_ui_port'])
    if proxy_port == admin_ui_port:
        print("Proxy port (%d) and admin UI port must not match. Aborting.", file=sys.stderr)
        exit(1)
    assistant_prefill_cull_thinkblock_patterns = cfg['assistant_prefill_cull_thinkblock_patterns']
    global_config['target_url'] = target_url
    global_config['assistant_prefill_cull_thinkblock_patterns'] = assistant_prefill_cull_thinkblock_patterns or []

    update_settings(new_url=global_config['target_url'], use_prefix=global_config['use_prefix'])

    logger.info("Global configuration: %s", global_config)

    # Launch Admin UI (Gradio)
    # Mount the Gradio UI onto the FastAPI app at the /ui endpoint
    gradio_launch_kws: dict[str, Any] = {
        'theme': gr_themes.Soft(),
    }
    gradio_app_hasauth = bool(os.getenv('ADMIN_UI_ENABLE_AUTH'))
    if gradio_app_hasauth:
        logger.info("Auth enabled for admin UI")
        gradio_app_username = os.getenv('ADMIN_UI_USERNAME')
        gradio_app_pw = os.getenv('ADMIN_UI_PASSWORD')
        if not gradio_app_username or not gradio_app_pw:
            logger.error(("ADMIN_UI_ENABLE_AUTH set, but one (or both) of"
                  "ADMIN_UI_USERNAME and ADMIN_UI_PASSWORD are not provided. Aborting."))
            exit(1)
        gradio_launch_kws['auth'] = (gradio_app_username, gradio_app_pw)

    logger.info("Launching Admin UI (Gradio)...")
    admin_ui.launch(server_name=admin_ui_host,
                    server_port=admin_ui_port,
                    root_path='/ui',
                    prevent_thread_lock=True,
                    quiet=False, **gradio_launch_kws)

    print("Starting Proxy Server...")
    print(f"Proxy Address: http://{proxy_host}:{proxy_port}")
    print(f"Admin UI:      http://{admin_ui_host}:{admin_ui_port}/ui")

    # Launch FastAPI server
    uvicorn.run(web, host=proxy_host, port=proxy_port)


if __name__ == "__main__":
    main()
