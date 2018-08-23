from __future__ import unicode_literals

import warnings

from .helpers import use_appropriate_encoding


class Channel:

    def __init__(self, account, channel_info):
        self._account = account
        self.channel_tag = channel_info.get("tag")

        for attr in ("name", "description", "created", "modified"):
            setattr(self, attr, channel_info.get(attr))

    def push_note(self, title, body):
        data = {"type": "note", "title": title, "body": body}
        return self._push(data)

    def push_address(self, name, address):
        warnings.warn("Address push type is removed. This push will be sent as note.")
        return self.push_note(name, address)

    def push_list(self, title, items):
        warnings.warn("List push type is removed. This push will be sent as note.")
        return self.push_note(title, ",".join(items))

    def push_link(self, title, url, body=None):
        data = {"type": "link", "title": title, "url": url, "body": body}
        return self._push(data)

    def push_file(self, file_name, file_url, file_type, body=None, title=None):
        return self._account.push_file(file_name, file_url, file_type, body=body, title=title, channel=self)

    def _push(self, data):
        data["channel_tag"] = self.channel_tag
        return self._account._push(data)

    @use_appropriate_encoding
    def __str__(self):
        return "Channel(name: '{0}' tag: '{1}')".format(self.name, self.channel_tag)

    def __repr__(self):
        return self.__str__()

    @property
    def name(self):
        return getattr(self, "name")

    @property
    def description(self):
        return getattr(self, "description")

    @property
    def created(self):
        return getattr(self, "created")

    @property
    def modified(self):
        return getattr(self, "modified")
