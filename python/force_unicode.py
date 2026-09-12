"""
Module which forces stdout/stderr into a mode which allows unicode output.
"""

import sys

try:
    sys.stdout.write("\u2603")
    sys.stdout.write("\b")
except UnicodeEncodeError:
    pass

try:
    sys.stderr.write("\u2603")
    sys.stderr.write("\b")
except UnicodeEncodeError:
    pass

if sys.stdout.encoding != "UTF-8" or sys.stderr.encoding != "UTF-8":
    from ctypes import c_char_p, py_object, pythonapi

    PyFile_SetEncoding = pythonapi.PyFile_SetEncoding
    PyFile_SetEncoding.argtypes = (py_object, c_char_p)

    if sys.stdout.encoding != "UTF-8":
        if not PyFile_SetEncoding(sys.stdout, "UTF-8"):
            raise SystemError(
                "Unable to force stdout to UTF-8, PyFile_SetEncoding failed."
            )

        if sys.stdout.encoding != "UTF-8":
            raise SystemError(
                f"Unable to force stdout to UTF-8, encoding still {sys.stdout.encoding}."
            )

    if sys.stderr.encoding != "UTF-8":
        if not PyFile_SetEncoding(sys.stderr, "UTF-8"):
            raise SystemError(
                "Unable to force stderr to UTF-8, PyFile_SetEncoding failed."
            )

        if sys.stderr.encoding != "UTF-8":
            raise SystemError(
                f"Unable to force stderr to UTF-8, encoding still {sys.stderr.encoding}."
            )

try:
    sys.stdout.write("\u2603")
    sys.stdout.write("\b")
except UnicodeEncodeError as e:
    raise SystemError(
        f"Unable to write unicode on stdout (encoding {sys.stdout.encoding}).\n{e}"
    )

try:
    sys.stderr.write("\u2603")
    sys.stderr.write("\b")
except UnicodeEncodeError as e:
    raise SystemError(
        f"Unable to write unicode on stderr (encoding {sys.stderr.encoding}).\n{e}"
    )
