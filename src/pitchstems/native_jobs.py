from __future__ import annotations

from dataclasses import dataclass
from multiprocessing import Process, Queue
from typing import Any, Callable


@dataclass(frozen=True)
class NativeJobMessage:
    kind: str
    token: int
    payload: dict[str, Any]

    def as_tuple(self) -> tuple[str, str, int, dict[str, Any]]:
        return ("NATIVE_JOB", self.kind, self.token, self.payload)


class NativeJobProcess:
    def __init__(self, token: int, process: Process, queue: Queue) -> None:
        self.token = token
        self.process = process
        self.queue = queue

    @classmethod
    def start(cls, token: int, target: Callable[[Queue, int], None]) -> NativeJobProcess:
        queue: Queue = Queue()
        process = Process(target=target, args=(queue, token), daemon=True)
        process.start()
        return cls(token=token, process=process, queue=queue)

    def is_alive(self) -> bool:
        return self.process.is_alive()

    def cancel(self, timeout_seconds: float = 5.0) -> None:
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout_seconds)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout_seconds)
