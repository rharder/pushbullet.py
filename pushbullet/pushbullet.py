import os
import json

import datetime
from pprint import pprint

import requests
import warnings

import time

from .device import Device
from .channel import Channel
from .chat import Chat
from .errors import PushbulletError, InvalidKeyError, PushError
from .filetype import get_file_type
from ._compat import standard_b64encode


class NoEncryptionModuleError(Exception):
    def __init__(self, msg):
        super(NoEncryptionModuleError, self).__init__(
            "cryptography is required for end-to-end encryption support and could not be imported: " + msg + "\nYou can install it by running 'pip install cryptography'")


class Pushbullet(object):
    DEVICES_URL = "https://api.pushbullet.com/v2/devices"
    CHATS_URL = "https://api.pushbullet.com/v2/chats"
    CHANNELS_URL = "https://api.pushbullet.com/v2/channels"
    ME_URL = "https://api.pushbullet.com/v2/users/me"
    PUSH_URL = "https://api.pushbullet.com/v2/pushes"
    UPLOAD_REQUEST_URL = "https://api.pushbullet.com/v2/upload-request"
    EPHEMERALS_URL = "https://api.pushbullet.com/v2/ephemerals"

    def __init__(self, api_key, encryption_password=None, proxy=None):
        self.api_key = api_key
        self._json_header = {'Content-Type': 'application/json'}

        self._session = requests.Session()
        self._session.auth = (self.api_key, "")
        self._session.headers.update(self._json_header)
        self._most_recent_timestamp = 0

        if proxy:
            if "https" not in [k.lower() for k in proxy.keys()]:
                raise ConnectionError("You can only use HTTPS proxies!")
            self._session.proxies.update(proxy)

        self.refresh()

        self._encryption_key = None
        if encryption_password:
            try:
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.hazmat.backends import default_backend
                from cryptography.hazmat.primitives import hashes
            except ImportError as e:
                raise NoEncryptionModuleError(str(e))

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self.user_info["iden"].encode("ASCII"),
                iterations=30000,
                backend=default_backend()
            )
            self._encryption_key = kdf.derive(encryption_password.encode("UTF-8"))

    # ################
    # IO Methods
    #

    def _http(self, func, url, **kwargs):
        """ All HTTP transactions funnel through here. """

        # If uploading a file, temporarily remove JSON header
        if "files" in kwargs:
            del self._session.headers["Content-Type"]
        try:
            resp = func(url, **kwargs)  # Do HTTP
        finally:
            self._session.headers.update(self._json_header)

        try:
            msg = resp.json()
        except:
            msg = resp.text

        return self._interpret_response(resp.status_code, resp.headers, msg)

    def _interpret_response(self, code, headers, msg):
        """ Interpret the HTTP response headers, raise exceptions, etc. """

        if code in (401, 403):
            raise InvalidKeyError()

        elif code == 429:
            epoch = int(headers.get("X-Ratelimit-Reset", 0))
            epoch_time = datetime.datetime.fromtimestamp(epoch).strftime('%c')
            raise PushbulletError(code, "Too Many Requests. " +
                                  "You have been ratelimited until {}".format(epoch_time))

        elif code not in (200, 204):  # 200 OK, 204 Empty response (file upload)
            raise PushbulletError(code, msg)

        if type(msg) is not dict:  # A dict is always returned
            msg = {"raw": msg}

        return msg

    def _get_data(self, url, **kwargs):
        """ HTTP GET """
        msg = self._http(self._session.get, url, **kwargs)
        return msg

    def _post_data(self, url, **kwargs):
        """ HTTP POST """
        msg = self._http(self._session.post, url, **kwargs)
        return msg

    def _delete_data(self, url, **kwargs):
        """ HTTP DELETE """
        msg = self._http(self._session.delete, url, **kwargs)
        return msg

    def _push(self, data):
        """ Helper for generic push """
        msg = self._post_data(Pushbullet.PUSH_URL, data=data)
        return msg

    @staticmethod
    def _recipient(device=None, chat=None, email=None, channel=None):
        data = dict()

        if device:
            data["device_iden"] = device.device_iden
        elif chat:
            data["email"] = chat.email
        elif email:
            data["email"] = email
        elif channel:
            data["channel_tag"] = channel.channel_tag

        return data

    # ################
    # Cached Data
    # - This data is retained locally rather than querying Pushbullet each time.

    def refresh(self):
        self._load_devices()
        self._load_chats()
        self._load_user_info()
        self._load_channels()
        self.get_pushes(limit=1)

    def _load_devices(self):
        self.devices = []

        resp_dict = self._get_data(self.DEVICES_URL)
        device_list = resp_dict.get("devices", [])

        for device_info in device_list:
            if device_info.get("active"):
                d = Device(self, device_info)
                self.devices.append(d)

    def _load_chats(self):
        self.chats = []

        resp_dict = self._get_data(self.CHATS_URL)
        chat_list = resp_dict.get("chats", [])

        for chat_info in chat_list:
            if chat_info.get("active"):
                c = Chat(self, chat_info)
                self.chats.append(c)

    def _load_user_info(self):
        self.user_info = self._get_data(self.ME_URL)

    def _load_channels(self):
        self.channels = []

        resp_dict = self._get_data(self.CHANNELS_URL)
        channel_list = resp_dict.get("channels", [])

        for channel_info in channel_list:
            if channel_info.get("active"):
                c = Channel(self, channel_info)
                self.channels.append(c)

    def get_device(self, nickname):
        req_device = next((device for device in self.devices if device.nickname == nickname), None)

        if req_device is None:
            raise PushbulletError('No device found with nickname "{}"'.format(nickname))

        return req_device

    def get_channel(self, channel_tag):
        req_channel = next((channel for channel in self.channels if channel.channel_tag == channel_tag), None)

        if req_channel is None:
            raise PushbulletError('No channel found with channel_tag "{}"'.format(channel_tag))

        return req_channel

    # ################
    # Device
    #

    def new_device(self, nickname, manufacturer=None, model=None, icon="system", func=None):
        gen = self._new_device(nickname, manufacturer=manufacturer, model=model, icon=icon)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data(self.DEVICES_URL, data=data)
        return next(gen)  # Post process response

    def _new_device(self, nickname, manufacturer=None, model=None, icon="system", func=None):
        data = {"nickname": nickname, "icon": icon}
        data.update({k: v for k, v in
                     (("model", model), ("manufacturer", manufacturer)) if v is not None})
        xfer = {"data": data}
        yield xfer  # Hand control back in order to conduct IO

        msg = xfer.get('msg', {})
        new_device = Device(self, msg)
        self.devices.append(new_device)
        yield new_device

    def edit_device(self, device, nickname=None, model=None, manufacturer=None, icon=None, has_sms=None):
        gen = self._edit_device(device, nickname=nickname, model=model,
                                manufacturer=manufacturer, icon=icon, has_sms=has_sms)
        xfer = next(gen)
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data("{}/{}".format(self.DEVICES_URL, device.device_iden), data=data)
        return next(gen)

    def _edit_device(self, device, nickname=None, model=None, manufacturer=None, icon=None, has_sms=None):
        data = {k: v for k, v in
                (("nickname", nickname or device.nickname), ("model", model),
                 ("manufacturer", manufacturer), ("icon", icon),
                 ("has_sms", has_sms)) if v is not None}
        if "has_sms" in data:
            data["has_sms"] = str(data["has_sms"]).lower()
        xfer = {"data": data}
        yield xfer

        msg = xfer.get('msg', {})
        new_device = Device(self, msg)
        self.devices[self.devices.index(device)] = new_device
        yield new_device

    def remove_device(self, device):
        msg = self._delete_data("{}/{}".format(self.DEVICES_URL, device.device_iden))
        return msg

    # ################
    # Chat
    #

    def new_chat(self, email):
        gen = self._new_chat(email)
        xfer = next(gen)
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data(self.CHATS_URL, data=data)
        return next(gen)

    def _new_chat(self, email):
        data = {"email": email}
        xfer = {"data": data}
        yield xfer

        msg = xfer.get('msg', {})
        new_chat = Chat(self, msg)
        self.chats.append(new_chat)
        yield new_chat

    def edit_chat(self, chat, muted=False):
        gen = self._edit_chat(chat, muted)
        xfer = next(gen)
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data("{}/{}".format(self.CHATS_URL, chat.iden), data=data)
        return next(gen)

    def _edit_chat(self, chat, muted=False):
        data = {"muted": muted}
        xfer = {"data": data}
        yield xfer

        msg = xfer.get('msg', {})
        new_chat = Chat(self, msg)
        self.chats[self.chats.index(chat)] = new_chat
        yield new_chat

    def remove_chat(self, chat):
        msg = self._delete_data("{}/{}".format(self.CHATS_URL, chat.iden))
        return msg

    # ################
    # Pushes
    #

    def get_pushes(self, modified_after=None, limit=None, filter_inactive=True):
        gen = self._get_pushes(modified_after=modified_after,
                               limit=limit, filter_inactive=filter_inactive)
        xfer = next(gen)
        resp = []
        while xfer["get_more_pushes"]:
            xfer["msg"] = self._get_data(self.PUSH_URL, params=xfer.get('data', {}))
            resp = next(gen)
        return resp

    def _get_pushes(self, modified_after=None, limit=None, filter_inactive=True):
        data = {}
        if modified_after is not None:
            data["modified_after"] = str(modified_after)
        if limit is not None:
            data["limit"] = int(limit)
        if filter_inactive:
            data['active'] = "true"

        pushes_list = []
        xfer = {"data": data}
        xfer["get_more_pushes"] = True
        while xfer["get_more_pushes"]:
            yield xfer  # IO happens...

            msg = xfer.get("msg", {})
            pushes_list += msg.get("pushes", [])
            if 'cursor' in msg and (not limit or len(pushes_list) < limit):
                data['cursor'] = msg['cursor']
            else:
                xfer["get_more_pushes"] = False

        if len(pushes_list) > 0 and pushes_list[0].get('modified', 0) > self._most_recent_timestamp:
            self._most_recent_timestamp = pushes_list[0]['modified']

        yield pushes_list

    def get_new_pushes(self, limit=None, filter_inactive=True):
        return self.get_pushes(modified_after=self._most_recent_timestamp,
                               limit=limit, filter_inactive=filter_inactive)

    def dismiss_push(self, iden):
        data = {"dismissed": True}
        msg = self._post_data("{}/{}".format(self.PUSH_URL, iden), data=data)
        return msg

    def delete_push(self, iden):
        msg = self._delete_data("{}/{}".format(self.PUSH_URL, iden))
        return msg

    def delete_pushes(self):
        msg = self._delete_data(self.PUSH_URL)
        return msg

    def upload_file(self, file_path, file_type=None):
        gen = self._upload_file(file_path, file_type=file_type)

        xfer = next(gen)  # Prep request params

        data = json.dumps(xfer["data"])
        xfer["msg"] = self._post_data(self.UPLOAD_REQUEST_URL, data=data)

        next(gen)  # Prep upload params

        with open(file_path, "rb") as f:
            xfer["msg"] = self._post_data(xfer["upload_url"], files={"file":f})

        return next(gen)  # Prep response

    def _upload_file(self, file_path, file_type=None):

        file_name = os.path.basename(file_path)
        if not file_type:
            with open(file_path, "rb") as f:
                file_type = get_file_type(f, file_path)
        data = {"file_name": file_name, "file_type": file_type}
        xfer = {"data": data}
        yield xfer  # Request upload

        msg = xfer["msg"]
        xfer["upload_url"] = msg.get("upload_url")  # Upload location
        file_url = msg.get("file_url")  # Final destination for downloading
        file_type = msg.get("file_type")  # What PB thinks is the filetype
        yield xfer  # Conduct upload

        yield {"file_type": file_type, "file_url": file_url, "file_name": file_name}

    def push_file(self, file_name, file_url, file_type, body=None, title=None, device=None, chat=None, email=None,
                  channel=None):
        gen = self._push_file(file_name, file_url, file_type, body=body, title=title,
                              device=device, chat=chat, email=email, channel=channel)
        xfer = next(gen)
        data = xfer.get("data")
        xfer["msg"] = self._push(json.dumps(data))
        return next(gen)

    def _push_file(self, file_name, file_url, file_type, body=None, title=None, device=None, chat=None, email=None,
              channel=None):
        data = {"type": "file", "file_type": file_type, "file_url": file_url, "file_name": file_name}
        if body:
            data["body"] = body

        if title:
            data["title"] = title
        data.update(Pushbullet._recipient(device, chat, email, channel))

        xfer = {"data": data}
        yield xfer

        msg = xfer.get("msg",{})
        yield msg

        return self._push(json.dumps(data))

    def push_note(self, title, body, device=None, chat=None, email=None, channel=None):
        data = {"type": "note", "title": title, "body": body}

        data.update(Pushbullet._recipient(device, chat, email, channel))

        return self._push(data)

    def push_address(self, name, address, device=None, chat=None, email=None):
        warnings.warn("Address push type is removed. This push will be sent as note.")
        return self.push_note(name, address, device, chat, email)

    def push_list(self, title, items, device=None, chat=None, email=None):
        warnings.warn("List push type is removed. This push will be sent as note.")
        return self.push_note(title, ",".join(items), device, chat, email)

    def push_link(self, title, url, body=None, device=None, chat=None, email=None, channel=None):
        data = {"type": "link", "title": title, "url": url, "body": body}

        data.update(Pushbullet._recipient(device, chat, email, channel))

        return self._push(data)

    def push_sms(self, device, number, message):
        data = {
            "type": "push",
            "push": {
                "type": "messaging_extension_reply",
                "package_name": "com.pushbullet.android",
                "source_user_iden": self.user_info['iden'],
                "target_device_iden": device.device_iden,
                "conversation_iden": number,
                "message": message
            }
        }

        if self._encryption_key:
            data["push"] = {
                "ciphertext": self._encrypt_data(data["push"]),
                "encrypted": True
            }

        r = self._session.post(self.EPHEMERALS_URL, data=json.dumps(data))
        if r.status_code == requests.codes.ok:
            return r.json()
        raise PushError(r.text)

    def _encrypt_data(self, data):
        assert self._encryption_key

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend

        iv = os.urandom(12)
        encryptor = Cipher(
            algorithms.AES(self._encryption_key),
            modes.GCM(iv),
            backend=default_backend()
        ).encryptor()

        ciphertext = encryptor.update(json.dumps(data).encode("UTF-8")) + encryptor.finalize()
        ciphertext = b"1" + encryptor.tag + iv + ciphertext
        return standard_b64encode(ciphertext).decode("ASCII")

    def _decrypt_data(self, data):
        assert self._encryption_key

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        from binascii import a2b_base64

        key = self._encryption_key
        encoded_message = a2b_base64(data)

        version = encoded_message[0:1]
        tag = encoded_message[1:17]
        initialization_vector = encoded_message[17:29]
        encrypted_message = encoded_message[29:]

        if version != b"1":
            raise Exception("Invalid Version")

        cipher = Cipher(algorithms.AES(key),
                        modes.GCM(initialization_vector, tag),
                        backend=default_backend())
        decryptor = cipher.decryptor()

        decrypted = decryptor.update(encrypted_message) + decryptor.finalize()
        decrypted = decrypted.decode()

        return (decrypted)

    def get_me(self):
        msg = self._get_data(Pushbullet.ME_URL)
        return msg
