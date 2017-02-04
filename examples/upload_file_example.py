#!/usr/bin/env python3
"""
Demonstrates how to upload and push a file.
"""
import asyncio
import sys

import logging

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
HTTP_PROXY_HOST = None
HTTP_PROXY_PORT = None


def main():
    """ Uses a callback scheduled on an event loop"""

    loop = asyncio.get_event_loop()
    pb = AsyncPushbullet(API_KEY, verify_ssl=False, loop=loop)
    loop.run_until_complete(upload_file(pb, __file__))


async def upload_file(pb: AsyncPushbullet, filename: str):
    info = await pb.async_upload_file(filename)

    # Push as a file:
    await pb.async_push_file(info["file_name"], info["file_url"], info["file_type"],
                             title="File Arrived!", body="Please enjoy your file")

    # Push as a link:
    await pb.async_push_link("Link to File Arrived!", info["file_url"], body="Please enjoy your file")

    await pb.close()


if __name__ == '__main__':
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    try:
        main()
    except KeyboardInterrupt:
        print("Quitting")
        pass
