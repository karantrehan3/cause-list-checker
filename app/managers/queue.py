import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional


@dataclass
class QueuedTask:
    """Represents a task in the queue."""

    method: Callable
    method_args: tuple
    method_kwargs: dict
    attempts: int = 0
    max_attempts: int = 3
    task_id: Optional[str] = None


class QueueManager:
    """Singleton queue manager for the application."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QueueManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.queue = asyncio.Queue()
            self.processor_task = None
            self.lock = asyncio.Lock()
            self._initialized = True

    async def start_processor(self):
        """Start the queue processor if not already running."""
        if self.processor_task is None or self.processor_task.done():
            self.processor_task = asyncio.create_task(self._queue_processor())
            print("Queue processor started", flush=True)

    async def stop_processor(self):
        """Stop the queue processor."""
        if self.processor_task and not self.processor_task.done():
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass
            print("Queue processor stopped", flush=True)

    async def add_task(
        self,
        method: Callable,
        *args,
        max_attempts: int = 3,
        task_id: Optional[str] = None,
        **kwargs,
    ):
        """Add a task to the queue."""
        task = QueuedTask(
            method=method,
            method_args=args,
            method_kwargs=kwargs,
            max_attempts=max_attempts,
            task_id=task_id or f"task_{datetime.now().timestamp()}",
        )
        await self.queue.put(task)
        print(f"Task {task.task_id} added to queue", flush=True)

    async def _queue_processor(self):
        """Background task that processes queued tasks one by one."""
        while True:
            try:
                # Wait for a task to be queued
                task = await self.queue.get()

                # Wait for the lock to be available
                while self.lock.locked():
                    await asyncio.sleep(15)

                # Process the task with retry logic
                success = False
                while task.attempts < task.max_attempts and not success:
                    task.attempts += 1

                    print(
                        f"Executing task {task.task_id} (attempt {task.attempts}/{task.max_attempts})",
                        flush=True,
                    )

                    try:
                        # Execute the method
                        if asyncio.iscoroutinefunction(task.method):
                            await task.method(*task.method_args, **task.method_kwargs)
                        else:
                            await asyncio.to_thread(
                                task.method, *task.method_args, **task.method_kwargs
                            )
                        success = True
                        print(f"Task {task.task_id} completed successfully", flush=True)

                    except Exception as e:
                        print(f"Task {task.task_id} failed: {e}", flush=True)
                        success = False

                        if task.attempts < task.max_attempts:
                            # Wait before retry: 45 seconds for first retry, 15 seconds for subsequent
                            wait_time = 45 if task.attempts == 1 else 15
                            print(
                                f"Task {task.task_id} failed, retrying in {wait_time} seconds...",
                                flush=True,
                            )
                            await asyncio.sleep(wait_time)

                if not success:
                    print(
                        f"Task {task.task_id} failed after {task.max_attempts} attempts",
                        flush=True,
                    )

                # Mark the task as done
                self.queue.task_done()

            except Exception as e:
                print(f"Error in queue processor: {e}", flush=True)
                await asyncio.sleep(5)  # Wait before continuing

    def get_queue_status(self) -> Dict[str, Any]:
        """Get the current status of the queue."""
        return {
            "queue_size": self.queue.qsize(),
            "processor_running": self.processor_task is not None
            and not self.processor_task.done(),
            "processor_done": (
                self.processor_task.done() if self.processor_task else None
            ),
            "lock_locked": self.lock.locked(),
        }


# Singleton instance
queue_manager = QueueManager()
