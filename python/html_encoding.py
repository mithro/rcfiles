#! /usr/bin/python
#
# Copyright 2009 Google Inc. All Rights Reserved.
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

"""A module for extracting the encoding from a HTTP/HTML page."""

import re


def findencoding(page):
    match = re.search("text/html; charset=([A-Za-z0-9-]+)", page)
    if not match:
        return None
    return match.groups()[0]


if __name__ == "__main__":
    assert findencoding('content="text/html; charset=gb2312;"') == "gb2312"
    assert (
        findencoding(
            '<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1" /> '
        )
        == "ISO-8859-1"
    )
    assert findencoding('<meta http-equiv="Content-Type" content="text/html;') is None
    assert findencoding("Content-Type: text/html") is None
    assert findencoding("Content-Type: text/html; charset=ISO-8859-1") == "ISO-8859-1"
    assert findencoding("Content-Type: text/html; charset=UTF-8") == "UTF-8"
