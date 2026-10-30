"""Addressed queue cancellation inside the native ComfyUI process."""

import re
import uuid

from aiohttp import web


def install_bridge():
    from server import PromptServer
    server = PromptServer.instance

    @server.routes.post("/moss-go/bridge/cancel")
    async def cancel(request):
        data = await request.json()
        job_id, prompt_id = data.get("job_id"), data.get("prompt_id")
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
            return web.json_response({"error": {"message": "Invalid job identifier."}}, status=400)
        try:
            uuid.UUID(prompt_id)
        except (ValueError, TypeError, AttributeError):
            return web.json_response({"error": {"message": "Invalid prompt identifier."}}, status=400)
        running, pending = server.prompt_queue.get_current_queue()
        def owned(item):
            return item[1] == prompt_id and item[3].get("extra_pnginfo", {}).get("moss_go", {}).get("job_id") == job_id
        if any(owned(item) for item in pending):
            if server.prompt_queue.delete_queue_item(owned):
                return web.json_response({"cancelled": True})
            # The worker may have started it since the snapshot was taken.
            running, _ = server.prompt_queue.get_current_queue()
        if any(owned(item) for item in running):
            addressed_interrupt = getattr(server.prompt_queue, "interrupt_if_running", None)
            if addressed_interrupt is None:
                return web.json_response({"error": {"message": "This ComfyUI version does not support addressed cancellation."}}, status=409)
            return web.json_response({"cancelled": bool(addressed_interrupt(prompt_id))})
        return web.json_response({"cancelled": False})
