import os
import sys

my_path = os.path.realpath(os.path.dirname(__file__))

python_path = []

# Try a relative path
python_path.append("/".join([my_path, "..", "python"]))
# Try in my home directory
python_path.append(os.path.expanduser("~/rcfiles/python"))
# Try an tansell's home directory
python_path.append(os.path.expanduser("~tansell/rcfiles/python"))
# Try an tim's home directory
python_path.append(os.path.expanduser("~tim/rcfiles/python"))


for path in python_path:
    path = os.path.realpath(path)
    if os.path.exists(path):
        sys.path.append(path)
        break
else:
    raise SystemError("Unable to find the rcfiles/python code.")
