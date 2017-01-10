import asyncio
from pprint import pprint

import aiohttp

__author__ = 'Igor Maculan <n3wtron@gmail.com>'

import logging
import time
import json
# from threading import Thread

# import requests
# import websockets  # https://github.com/aaugustin/websockets

log = logging.getLogger('pushbullet.Listener')

WEBSOCKET_URL = 'wss://stream.pushbullet.com/websocket/'


class Listener():
    def __init__(self, account,
                 on_push=None,
                 on_error=None):#,
                 # http_proxy_host=None,
                 # http_proxy_port=None):
        """
        :param api_key: pushbullet Key
        :param on_push: function that get's called on all pushes
        :param http_proxy_host: host proxy (ie localhost)
        :param http_proxy_port: host port (ie 3128)
        """
        self._account = account
        self._api_key = self._account.api_key
        self.on_error = on_error

        self.connected = False
        self._ws = None  # type: aiohttp.ClientWebSocketResponse
        self.last_update = time.time()

        self.on_push = on_push

        # History
        self.history = None
        self.clean_history()

        # TODO: Proxies
        # proxy configuration
        # self.http_proxy_host = http_proxy_host
        # self.http_proxy_port = http_proxy_port
        # self.proxies = None
        # if http_proxy_port is not None and http_proxy_port is not None:
        #     self.proxies = {
        #         "http": "http://" + http_proxy_host + ":" + str(http_proxy_port),
        #         "https": "http://" + http_proxy_host + ":" + str(http_proxy_port),
        #     }

    def clean_history(self):
        self.history = []

    async def close(self):
        if self.connected:
            await self._ws.close()

    def on_open(self, ws):
        log.debug("on_open")
        self.connected = True
        self.last_update = time.time()

    def on_close(self, ws):
        log.debug('Listener closed')
        print("close")
        self.connected = False

    async def on_message(self, ws, msg):
        log.debug('Message received:' + str(msg))
        try:
            if msg["type"] != "nop" and callable(self.on_push):
                await self.on_push(msg)
        except Exception as e:
            logging.exception(e)

    def connect(self):
        asyncio.ensure_future(self._ws_monitor())

    async def _ws_monitor(self):
        """ Loops, listening for new messages from web socket. """
        async with self._account._aio_session.ws_connect(WEBSOCKET_URL + self._api_key) as self._ws:
            self.on_open(self._ws)
            async for msg in self._ws:
                self.last_update = time.time()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self.on_message(self._ws, json.loads(msg.data))
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.on_close(ws)
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break
        print("ws with loop complete", flush=True)

