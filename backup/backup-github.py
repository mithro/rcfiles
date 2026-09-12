#!/usr/bin/python

import json
import os
import subprocess

import urllib2

root = os.path.dirname(__file__)
if not root:
    root = "."
root = os.path.realpath(root)

os.chdir(root)

for user in ["mithro", "timsvideo"]:
    f = urllib2.urlopen(f"https://github.com/api/v2/json/repos/show/{user}")
    data = json.load(f)
    for repo in data["repositories"]:
        url = repo["url"].replace("https://", "git+ssh://git@")
        if not os.path.exists(repo["name"] + ".git"):
            subprocess.call(f"git clone --bare {url}", shell=True)
        else:
            subprocess.call(
                "cd {}.git; git fetch {} +refs/heads/*:+refs/heads/*".format(repo["name"], url),
                shell=True,
            )
