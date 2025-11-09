#!/usr/bin/env python3
#
# Copyright 2008 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Convert HTTP headers into a dictionary.
"""

class HTTPHeaders(dict):
  def __init__(self, values):
    for header in values.split("\n"):
      if ':' not in header:
        continue
      key, value = header.split(': ', 1)
      if ';' in value:
        parts = value.strip().split('; ')
        for i in range(0, len(parts)):
          if '=' in parts[i]:
            parts[i] = parts[i].split('=')
        value = parts
      self[key] = value


if __name__ == "__main__":
  a = HTTPHeaders("""\
HTTP/1.1 200 OK
Date: Tue, 18 Nov 2008 06:23:46 GMT
Server: Apache/2.2.3 (Debian) DAV/2 SVN/1.4.2 mod_ssl/2.2.3 OpenSSL/0.9.8c mod_wsgi/2.3 Python/2.4.4
Last-Modified: Fri, 22 Feb 2008 12:57:44 GMT
ETag: "13e06e4-447d-c4a94200"
Accept-Ranges: bytes
Content-Length: 17533
Content-Type: text/html; charset=UTF-8
""")
  print(a)
