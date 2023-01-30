import logging
from queue import Queue
from threading import Lock

from bija.args import LOGGING_LEVEL
from bija.task_kinds import TaskKind

logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class Task:
    def __init__(self, kind: TaskKind, data: object) -> None:
        logger.info('TASK kind: {}'.format(kind))
        self.kind = kind
        self.data = data


class TaskPool:
    def __init__(self) -> None:
        logger.info('START TASK POOL')
        self.tasks: Queue[Task] = Queue()
        self.lock: Lock = Lock()

    def add(self, kind: TaskKind, data: object):
        logger.info('ADD task')
        self.tasks.put(Task(kind, data))

    def get(self):
        logger.info('GET task')
        return self.tasks.get()

    def has_tasks(self):
        return self.tasks.qsize() > 0


class DeferredTasks:

    def __init__(self) -> None:
        logger.info('DEFERRED TASKS')
        self.pool = TaskPool()

    def next(self) -> Task | None:
        if self.pool.has_tasks():
            logger.info('NEXT task')
            return self.pool.get()
        return None

