#! /usr/bin/env python
# Reading the cookie's from Firefox/Mozilla. Supports Firefox 3.0 and Firefox 2.x
#
# Author: Noah Fontes <nfontes AT cynigram DOT com>,
#         Tim Ansell <mithro AT mithis DOT com>
# License: MIT

def sqlite2cookie(filename):
    from cStringIO import StringIO
    try:
      from pysqlite2 import dbapi2 as sqlite
    except ImportError:
      import sqlite3 as sqlite

    con = sqlite.connect(filename)
    con.text_factory = str
    cur = con.cursor()
    cur.execute("select host, path, isSecure, expiry, name, value from moz_cookies")

    ftstr = ["FALSE","TRUE"]

    s = StringIO()
    s.write("""\
# Netscape HTTP Cookie File
# http://www.netscape.com/newsref/std/cookie_spec.html
# This is a generated file!  Do not edit.
""")
    for item in cur.fetchall():
        s.write("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
            item[0], ftstr[item[0].startswith('.')], item[1],
            ftstr[item[2]], item[3], item[4], item[5]))

    s.seek(0)

    cookie_jar = cookielib.MozillaCookieJar()
    cookie_jar._really_load(s, '', True, True)
    return cookie_jar

import cookielib
import firefox_finder
import os
import sys

def get_cookie_jar():
    profile_dir = firefox_finder.get_profile_dir()
    if os.path.join(profile_dir, 'cookies.sqlite'):
        cookie_jar = os.path.join(profile_dir, 'cookies.sqlite')
    elif os.path.join(profile_dir, 'cookies.txt'):
        cookie_jar = os.path.join(profile_dir, 'cookies.txt')

    if cookie_jar.endswith('.sqlite'):
        return sqlite2cookie(cookie_jar)
    else:
        return cookielib.MozillaCookieJar(cookie_jar)

def get_cookie_jar_interactive():
    profile_dir = firefox_finder.get_profile_dir()
    if os.path.join(profile_dir, 'cookies.sqlite'):
        cookie_jar = os.path.join(profile_dir, 'cookies.sqlite')
    elif os.path.join(profile_dir, 'cookies.txt'):
        cookie_jar = os.path.join(profile_dir, 'cookies.txt')

    path = raw_input('Path to cookie jar file [%s]: ' % cookie_jar)
    if path.strip():
        # Some input specified, set it
        cookie_jar = os.path.realpath(os.path.expanduser(path.strip()))

    if cookie_jar.endswith('.sqlite'):
        return sqlite2cookie(cookie_jar)
    else:
        return cookielib.MozillaCookieJar(cookie_jar)

if __name__ == "__main__":
    import pprint
    for cookie in get_cookie_jar_interactive():
      print cookie
