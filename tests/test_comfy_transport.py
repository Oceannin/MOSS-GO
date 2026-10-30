import unittest

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

from moss_go.comfy import ComfyClient
from moss_go.errors import StudioError


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        async def broken(request):
            self.requests.append((request.method, request.path))
            return web.Response(text="truncated JSON", content_type="application/json")
        async def unavailable(request):
            return web.Response(status=503)
        app = web.Application()
        app.router.add_post("/prompt", broken)
        app.router.add_post("/upload/image", broken)
        app.router.add_get("/view", unavailable)
        self.server = TestServer(app)
        await self.server.start_server()
        self.client = ComfyClient(str(self.server.make_url("")))
        self.client.session = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()

    async def test_a_truncated_acceptance_response_is_uncertain_and_not_automatically_posted_again(self):
        with self.assertRaises(StudioError) as caught:
            await self.client.json("/prompt", {"prompt": {}})
        self.assertEqual(caught.exception.code, "submission_uncertain")
        self.assertEqual(self.requests, [("POST", "/prompt")])

    async def test_a_broken_upload_response_is_retryable_before_generation(self):
        with self.assertRaises(StudioError) as caught:
            await self.client.upload(b"image", "input.png")
        self.assertEqual(caught.exception.code, "comfy_unavailable")

    async def test_a_temporarily_unavailable_finished_image_is_retryable(self):
        with self.assertRaises(StudioError) as caught:
            await self.client.image({"filename": "result.png", "type": "output"})
        self.assertEqual(caught.exception.code, "comfy_unavailable")
