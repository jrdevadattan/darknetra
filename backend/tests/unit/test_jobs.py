import asyncio
import unittest


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def test_deduplication_and_concurrency(self):
        from darknetra.jobs.runner import InProcessRunner

        runner = InProcessRunner(max_workers=1)
        release = asyncio.Event()
        started = asyncio.Event()
        calls = []

        async def work():
            calls.append("work")
            started.set()
            await release.wait()

        first = await runner.submit("ingest", work, key="case:one")
        duplicate = await runner.submit("ingest", work, key="case:one")
        second = await runner.submit("other", work, key="case:two")
        await started.wait()
        self.assertEqual(first, duplicate)
        self.assertNotEqual(first, second)
        self.assertEqual(calls, ["work"])
        release.set()
        await runner.wait_all()
        self.assertEqual(calls, ["work", "work"])
        self.assertEqual((await runner.status(first)).status, "DONE")
        await runner.shutdown()

    async def test_failure_and_key_retry(self):
        from darknetra.jobs.runner import InProcessRunner

        runner = InProcessRunner()

        async def broken():
            raise ValueError("sensitive details")

        first = await runner.submit("ingest", broken, key="same")
        await runner.wait_all()
        result = await runner.status(first)
        self.assertEqual(result.status, "FAILED")
        self.assertNotIn("sensitive", result.error)
        second = await runner.submit("ingest", broken, key="same")
        self.assertNotEqual(second, first)
        await runner.shutdown()
