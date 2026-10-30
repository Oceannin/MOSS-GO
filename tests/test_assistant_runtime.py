import asyncio
import json
import unittest

from aiohttp import web
from aiohttp.test_utils import TestServer

from moss_go.assistant import MODEL, MODEL_DIGEST, PromptAssistant
from moss_go.errors import StudioError


class AssistantRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.digest = MODEL_DIGEST
        self.reason = "stop"
        self.reply = "A red cup on a gray table."
        self.requests = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        async def tags(request):
            return web.json_response({"models": [{"name": MODEL, "digest": self.digest}]})
        async def chat(request):
            self.requests.append(await request.json())
            self.started.set()
            await self.release.wait()
            return web.json_response({"done": True, "done_reason": self.reason, "message": {"content": json.dumps({"prompt": self.reply})}})
        app = web.Application()
        app.router.add_get("/api/tags", tags)
        app.router.add_post("/api/chat", chat)
        self.server = TestServer(app)
        await self.server.start_server()
        self.assistant = PromptAssistant(str(self.server.make_url("")))

    async def asyncTearDown(self):
        self.release.set()
        await self.server.close()

    async def test_only_the_pinned_model_is_ready_and_requests_stay_on_cpu(self):
        result = await self.assistant.enhance("A red cup on a gray table.")
        self.assertFalse(result["applied"])
        self.assertEqual(result["model_digest"], MODEL_DIGEST)
        payload = self.requests[0]
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["options"]["num_gpu"], 0)
        self.assertEqual(payload["keep_alive"], 0)

    async def test_a_changed_model_revision_cannot_be_used_silently(self):
        self.digest = "f" * 64
        self.assertFalse((await self.assistant.status())["ready"])
        with self.assertRaises(StudioError) as caught:
            await self.assistant.enhance("A red cup.")
        self.assertEqual(caught.exception.code, "assistant_unavailable")
        self.assertEqual(self.requests, [])

    async def test_traits_remain_separate_and_are_attached_exactly_once(self):
        character = {"hair": "short silver hair"}
        result = await self.assistant.enhance("A red cup on a gray table.", character)
        self.assertEqual(result["protected_character"], character)
        self.assertNotIn("short silver hair", result["suggestion"])
        self.assertEqual(result["generation_prompt"].count("short silver hair"), 1)
        self.assertEqual(character, {"hair": "short silver hair"})
        self.assertEqual(json.loads(self.requests[0]["messages"][-1]["content"]), {"image_description": "A red cup on a gray table."})

    async def test_model_injected_traits_are_rejected_instead_of_duplicated(self):
        self.reply = "A red cup near a character with short silver hair."
        with self.assertRaises(StudioError) as caught:
            await self.assistant.enhance("A red cup.", {"hair": "short silver hair"})
        self.assertEqual(caught.exception.code, "assistant_changed_intent")

    async def test_truncated_suggestions_are_not_offered_for_apply(self):
        self.reason = "length"
        with self.assertRaises(StudioError) as caught:
            await self.assistant.enhance("A red cup.")
        self.assertEqual(caught.exception.code, "assistant_incomplete")

    async def test_a_second_suggestion_does_not_start_another_model_request(self):
        self.release.clear()
        first = asyncio.create_task(self.assistant.enhance("A red cup."))
        await self.started.wait()
        with self.assertRaises(StudioError) as caught:
            await self.assistant.enhance("A second cup.")
        self.assertEqual(caught.exception.code, "assistant_busy")
        self.release.set()
        await first
        self.assertEqual(len(self.requests), 1)
