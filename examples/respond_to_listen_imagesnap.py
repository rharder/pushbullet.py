#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Experimental script that responds to a ListenApp exec command.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

ENCODING = "utf-8"
API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


def main():
    recvd_push = json.loads(sys.stdin.read())  # Throw whatever exceptions to stderr

    if recvd_push.get("body", "").lower().strip() == "imagesnap":

        # Temp file to house the image file
        temp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_img.close()

        try:

            # Take a picture and upload
            # PRETEND TO TAKE A PICTURE
            import shutil
            fakepic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot.jpg")
            shutil.copy(fakepic, temp_img.name)

            # Take a picture
            # proc = subprocess.run(["imagesnap", temp_img.name],
            proc = subprocess.run(["notepad.exe"],  # Debugging
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  timeout=10,
                                  encoding=ENCODING)

            # Upload picture
            with AsyncPushbullet(API_KEY, proxy=PROXY) as pb:
                # resp = pb.upload_file(temp_img.name)  # Upload here
                resp = pb.upload_file_to_transfer_sh(temp_img.name)  # Upload here
            del pb

            file_type = resp.get("file_type")
            file_url = resp.get("file_url")
            file_name = resp.get("file_name")

            # Provide a response via stdout
            stdout_txt = proc.stdout
            stderr_txt = proc.stderr
            myresp = {
                "type": "file",
                "title": "Imagesnap",
                "body": "{}\n{}".format(stdout_txt, stderr_txt).strip(),
                "file_name": file_name,
                "file_type": file_type,
                "file_url": file_url,
                "received_push": recvd_push
            }
            dev_iden = recvd_push.get("source_device_iden")
            if dev_iden is not None:
                myresp["device_iden"] = dev_iden

            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "response.json"), "w") as fout:
                fout.write(json.dumps(myresp, indent=4))

            print(json.dumps(myresp), flush=True)

        except Exception as e:
            # raise e
            print("Error:", e, file=sys.stderr)

        finally:

            os.remove(temp_img.name)


if __name__ == "__main__":

    if "PUSHBULLET_API_KEY" in os.environ:
        API_KEY = os.environ["PUSHBULLET_API_KEY"].strip()

    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    main()
