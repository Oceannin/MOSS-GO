import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from moss_go.bridge import install_bridge


PROMPT = "43131655-5a66-4a35-8cbc-eddd120b9b09"
JOB = "a" * 32


class Queue:
    def __init__(self):
        self.running, self.pending, self.interrupted = [], [], []
        self.interrupt_result = True
        self.move_before_delete = False

    def get_current_queue(self):
        return self.running[:], self.pending[:]

    def delete_queue_item(self, predicate):
        if self.move_before_delete:
            self.running, self.pending = self.pending, []
            return False
        matched = any(predicate(item) for item in self.pending)
        self.pending = [item for item in self.pending if not predicate(item)]
        return matched

    def interrupt_if_running(self, prompt_id):
        self.interrupted.append(prompt_id)
        return self.interrupt_result


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.queue = Queue()
        self.item = [0, PROMPT, {}, {"extra_pnginfo": {"moss_go": {"job_id": JOB}}}]
        server = SimpleNamespace(routes=web.RouteTableDef(), prompt_queue=self.queue)
        with patch.dict(sys.modules, {"server": SimpleNamespace(PromptServer=SimpleNamespace(instance=server))}):
            install_bridge()
        app = web.Application()
        app.add_routes(server.routes)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def cancel(self, job_id=JOB):
        response = await self.client.post("/moss-go/bridge/cancel", json={"prompt_id": PROMPT, "job_id": job_id})
        self.assertEqual(response.status, 200)
        return await response.json()

    async def test_wrong_ownership_never_reaches_the_interrupt(self):
        self.queue.running = [self.item]
        self.assertFalse((await self.cancel("b" * 32))["cancelled"])
        self.assertEqual(self.queue.interrupted, [])

    async def test_an_atomic_interrupt_that_lost_the_finish_race_is_not_reported_as_success(self):
        self.queue.running = [self.item]
        self.queue.interrupt_result = False
        self.assertFalse((await self.cancel())["cancelled"])

    async def test_a_queued_job_that_started_during_cancellation_is_addressed_safely(self):
        self.queue.pending = [self.item]
        self.queue.move_before_delete = True
        self.assertTrue((await self.cancel())["cancelled"])
        self.assertEqual(self.queue.interrupted, [PROMPT])

    async def test_deleting_one_pending_job_keeps_unrelated_items(self):
        external = [1, "e8a0560c-2a45-400d-a868-d848b29c1046", {}, {}]
        self.queue.pending = [self.item, external]
        self.assertTrue((await self.cancel())["cancelled"])
        self.assertEqual(self.queue.pending, [external])
        self.assertEqual(self.queue.interrupted, [])
