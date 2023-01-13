import json
import logging
import urllib
from enum import IntEnum
from queue import Queue
from threading import Lock
from urllib import request
from urllib.error import HTTPError, URLError
from socket import timeout
from urllib.request import Request

import validators
from bs4 import BeautifulSoup

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.settings import SETTINGS

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class TaskKind(IntEnum):
    FETCH_OG = 1


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

    def next(self) -> None:
        if self.pool.has_tasks():
            logger.info('NEXT task')
            task = self.pool.get()
            if task.kind == TaskKind.FETCH_OG:
                OGTags(task.data)


class OGTags:

    def __init__(self, data):
        logger.info('OG TAGS')
        self.note_id = data['note_id']
        self.url = data['url']
        self.og = {}
        self.note = DB.get_note(SETTINGS.get('pubkey'), self.note_id)

        response = self.fetch()
        if response:
            self.process(response)

    def fetch(self):
        logger.info('fetch for {}'.format(self.url))
        req = Request(self.url, headers={'User-Agent': 'Bija Nostr Client'})
        try:
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    return response.read()
                return False
        except HTTPError as error:
            print(error.status, error.reason)
            return False
        except URLError as error:
            print(error.reason)
            return False
        except TimeoutError:
            print("Request timed out")
            return False

    def process(self, response):
        logger.info('process {}'.format(self.url))
        if response is not None:
            soup = BeautifulSoup(response, 'html.parser')
            for prop in ['image', 'title', 'description', 'url']:
                item = soup.find("meta", property="og:{}".format(prop))
                if item is not None:
                    content = item.get("content")
                    if content is not None:
                        if prop in ['url', 'image']:
                            if validators.url(content):
                                self.og[prop] = content
                        else:
                            self.og[prop] = content

            if len(self.og) > 0:
                if 'url' not in self.og:
                    self.og['url'] = self.url
                self.store()

    def store(self):
        logger.info('store OG')
        media = json.loads(self.note['media'])
        media.append([self.og, 'og'])
        DB.update_note_media(self.note_id, json.dumps(media))
