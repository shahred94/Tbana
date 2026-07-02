"""LiveTrigger Smart Gift Queue Manager."""

import asyncio
import threading
import time

from app.actions.executor import (
    action_executor
)

from app.storage.sqlite_store import (
    get_setting
)
from app.core.activity import activity_feed

class GiftQueueManager:
    """Manage separate queue for each gift."""


    def __init__(self):

        self.queues = {}

        self.workers = {}
        self.paused = False

        self.loop = (
            asyncio.new_event_loop()
        )

        self.thread = (
            threading.Thread(
                target=self.start_loop,
                daemon=True,
            )
        )

        self.thread.start()

    def start_loop(
        self,
    ):

        """Run background asyncio loop."""

        asyncio.set_event_loop(
            self.loop
        )

        self.loop.run_forever()

    def get_queue(
        self,
        gift_name: str,
    ):

        """Get or create gift queue."""


        if gift_name not in self.queues:

            self.queues[gift_name] = (
                asyncio.Queue()
            )

            print(
                "[QUEUE] Created queue:",
                gift_name
            )


        return self.queues[
            gift_name
        ]


    def get_delay(
        self,
        gift_name: str,
    ) -> float:

        """Get queue delay in seconds."""


        value = get_setting(
            f"gift_queue_delay_ms:{gift_name}"
        )


        if value is None:

            return 0


        try:

            return (
                int(value) / 1000
            )


        except ValueError:

            return 0


    async def add_job(
        self,
        gift_name: str,
        job: dict,
    ):

        """Add gift job into queue."""

        queue = self.get_queue(
            gift_name
        )

        await queue.put(
            job
        )

        print(
            "[QUEUE] Added:",
            gift_name,
            "Pending:",
            queue.qsize()
        )

        self.start_worker(
            gift_name
        )


    def add_job_sync(
        self,
        gift_name: str,
        job: dict,
    ):

        """Add job from sync code."""

        asyncio.run_coroutine_threadsafe(
            self.add_job(
                gift_name,
                job,
            ),
            self.loop,
        )


    def start_worker(
        self,
        gift_name: str,
    ):

        """Start worker for gift queue."""

        if gift_name in self.workers:

            return

        print(
            "[QUEUE] Starting worker:",
            gift_name
        )

        self.workers[gift_name] = (
            asyncio.create_task(
                self.worker(
                    gift_name
                )
            )
        ) 

    async def worker(
        self,
        gift_name: str,
    ):

        """Process jobs from gift queue."""

        queue = self.get_queue(
            gift_name
        )

        print(
            "[QUEUE] Worker running:",
            gift_name
        )

        while True:

            job = await queue.get()

            while self.paused:
                await asyncio.sleep(
                    0.1
                )

            print(
                "[QUEUE] Processing:",
                gift_name
            )

            actions = job.get(
                "actions",
                []
            )

            max_duration = self.action_max_duration(
                actions
            )

            deadline = (
                time.monotonic() + max_duration
                if max_duration > 0
                else None
            )

            for action in job.get(
                "actions",
                []
            ):

                if (
                    deadline is not None
                    and
                    time.monotonic() >= deadline
                ):

                    print(
                        "[QUEUE] Action duration reached; skipping remaining steps."
                    )

                    break

                print(
                    "[QUEUE] Executing action_step:",
                    action.get(
                        "_step_order"
                    ),
                    action.get(
                        "type"
                    ),
                    "from",
                    action.get(
                        "_action_preset_name"
                    )
                )

                action_executor.execute(
                    action,
                    deadline=deadline,
                )

            delay = self.get_delay(
                gift_name
            )

            if delay > 0:

                print(
                    "[QUEUE] Delay:",
                    gift_name,
                    delay,
                    "seconds"
                )

                await asyncio.sleep(
                    delay
                )

            print(
                "[DEBUG] Sleep finished:",
                gift_name
            )
            queue.task_done()

            activity_feed.record(
                "queue",
                "completed",
                f"{gift_name} queue completed",
                ", ".join(
                    dict.fromkeys(
                        str(
                            action.get(
                                "_action_preset_name",
                                action.get("type", "Action"),
                            )
                        )
                        for action in actions
                    )
                ),
                job.get("user", ""),
            )
            
            print(
                "[DEBUG] Task done:",
                gift_name,
                "Pending:",
                queue.qsize()
)            

            if queue.empty():

                print(
                    "[QUEUE] Worker stopped:",
                    gift_name
                )

                self.workers.pop(
                    gift_name,
                    None
                )

                break

    def pause(self) -> None:
        """Pause workers before their next queued action."""

        self.paused = True
        activity_feed.record(
            "queue",
            "paused",
            "Gift queues paused",
        )

    def resume(self) -> None:
        """Resume paused workers."""

        self.paused = False
        activity_feed.record(
            "queue",
            "resumed",
            "Gift queues resumed",
        )

    async def _clear(
        self,
        gift_name: str | None = None,
    ) -> int:
        """Remove pending jobs while leaving a running job intact."""

        cleared = 0
        names = (
            [gift_name]
            if gift_name is not None
            else list(self.queues)
        )

        for name in names:
            queue = self.queues.get(name)
            if queue is None:
                continue

            while True:
                try:
                    queue.get_nowait()
                    queue.task_done()
                    cleared += 1
                except asyncio.QueueEmpty:
                    break

        return cleared

    def clear(
        self,
        gift_name: str | None = None,
    ) -> int:
        """Synchronously clear pending jobs from API threads."""

        future = asyncio.run_coroutine_threadsafe(
            self._clear(gift_name),
            self.loop,
        )
        cleared = future.result(
            timeout=3
        )
        activity_feed.record(
            "queue",
            "cleared",
            (
                f"{gift_name} queue cleared"
                if gift_name
                else "All gift queues cleared"
            ),
            f"{cleared} pending job(s) removed",
        )
        return cleared

    @staticmethod
    def action_max_duration(
        actions: list[dict],
    ) -> float:

        """Return the action preset duration shared by queued steps."""

        for action in actions:

            try:

                duration = float(
                    action.get(
                        "max_duration",
                        0,
                    )
                    or
                    0
                )

            except (
                TypeError,
                ValueError,
            ):

                duration = 0

            if duration > 0:

                return duration

        return 0

    def get_status(
        self,
    ) -> dict:

        """Get current queue status."""

        status = {}


        for gift_name, queue in self.queues.items():

            delay = self.get_delay(
                gift_name
            )

            estimated_wait = 0.0
            for job in list(
                getattr(
                    queue,
                    "_queue",
                    [],
                )
            ):
                estimated_wait += (
                    self.action_max_duration(
                        job.get(
                            "actions",
                            [],
                        )
                    )
                    + delay
                )

            status[gift_name] = {
                "pending": queue.qsize(),
                "running": (
                    gift_name in self.workers
                ),
                "paused": self.paused,
                "delay_seconds": delay,
                "estimated_wait_seconds": round(
                    estimated_wait,
                    1,
                ),
            }


        return status
# Global Queue Manager
gift_queue_manager = (
    GiftQueueManager()
)
