#!/usr/bin/env python3
import os
import sys
sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import Pushbullet

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY


def main():
    proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
    pb = Pushbullet(API_KEY, proxy=proxy)

    title = "Greetings"
    body = "Welcome to accessing Pushbullet with Python"
    pb.push_note(title, body)


if __name__ == "__main__":
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    main()
