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
from bija.db import BijaDB

DB = BijaDB(app.session)


class TaskKind(IntEnum):
    FETCH_OG = 1


class Task:
    def __init__(self, kind: TaskKind, data: object) -> None:
        self.kind = kind
        self.data = data


class TaskPool:
    def __init__(self) -> None:
        self.tasks: Queue[Task] = Queue()
        self.lock: Lock = Lock()

    def add(self, kind: TaskKind, data: object):
        print('add task')
        self.tasks.put(Task(kind, data))

    def get(self):
        return self.tasks.get()

    def has_tasks(self):
        return self.tasks.qsize() > 0


class DeferredTasks:

    def __init__(self) -> None:
        self.pool = TaskPool()

    def next(self) -> None:
        if self.pool.has_tasks():
            task = self.pool.get()
            print('fetch og for:', task.data['url'])
            if task.kind == TaskKind.FETCH_OG:
                OGTags(task.data)


class OGTags:

    def __init__(self, data):
        self.note_id = data['note_id']
        self.url = data['url']
        self.og = {}
        self.note = DB.get_note(self.note_id)

        response = self.fetch()
        if response:
            self.process(response)

    def fetch(self):
        req = Request(self.url, headers={'User-Agent': 'Bija Nostr Client'})
        try:
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    print(response.status)
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
        media = json.loads(self.note['media'])
        media.append([self.og, 'og'])
        DB.update_note_media(self.note_id, json.dumps(media))
