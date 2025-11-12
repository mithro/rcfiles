#!/usr/bin/python

import urllib2
import json
import os
import subprocess

root = os.path.dirname(__file__)
if not root:
    root = "."
root = os.path.realpath(root)

os.chdir(root)

for user in ["mithro", "timsvideo"]:
    f = urllib2.urlopen("https://github.com/api/v2/json/repos/show/%s" % user)
    data = json.load(f)
    for repo in data["repositories"]:
        url = repo["url"].replace("https://", "git+ssh://git@")
        if not os.path.exists(repo["name"] + ".git"):
            subprocess.call("git clone --bare %s" % url, shell=True)
        else:
            subprocess.call(
                "cd %s.git; git fetch %s +refs/heads/*:+refs/heads/*"
                % (repo["name"], url),
                shell=True,
            )
