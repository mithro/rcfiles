#! /usr/bin/env python
# Reading the cookie's from Firefox/Mozilla. Supports Firefox 3.0 and Firefox 2.x
#
# Author: Noah Fontes <nfontes AT cynigram DOT com>,
#         Tim Ansell <mithro AT mithis DOT com>
# License: MIT

import os
import sys
import logging
import ConfigParser

# Set up cookie jar paths
def _get_firefox_profile_dir (path):
    profiles_ini = os.path.join(path, 'profiles.ini')
    if not os.path.exists(path) or not os.path.exists(profiles_ini):
        return None

    # Open profiles.ini and read the path for the first profile
    profiles_ini_reader = ConfigParser.ConfigParser();
    profiles_ini_reader.readfp(open(profiles_ini))
    profile_name = profiles_ini_reader.get('Profile0', 'Path', True)

    profile_path = os.path.join(path, profile_name)
    if not os.path.exists(profile_path):
        return None
    else:
        return profile_path

def _get_firefox_nt_profile_dir ():
    # See http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/473846
    try:
        import _winreg
        import win32api
    except ImportError:
        logging.error('Cannot load winreg -- running windows and win32api loaded?')
    key = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders')
    try:
        ret = _winreg.QueryValueEx(key, 'AppData')
    except WindowsError:
        return None
    else:
        key.Close()
        if result[1] == _winreg.REG_EXPAND_SZ:
            result = win32api.ExpandEnvironmentStrings(result[0])
        else:
            result = result[0]

    return _get_firefox_profile_dir(os.path.join(result, r'Mozilla\Firefox\Profiles'))

def _get_firefox_posix_profile_dir ():
    return _get_firefox_profile_dir(os.path.expanduser(r'~/.mozilla/firefox'))

def _get_firefox_mac_profile_dir ():
    # First of all...
    result = _get_firefox_profile_dir(os.path.expanduser(r'~/Library/Mozilla/Firefox/Profiles'))
    if result == None:
        result = _get_firefox_profile_dir(os.path.expanduser(r'~/Library/Application Support/Firefox/Profiles'))
    return result

FIREFOX_COOKIE_JARS = {
    'nt': _get_firefox_nt_profile_dir,
    'posix': _get_firefox_posix_profile_dir,
    'mac': _get_firefox_mac_profile_dir
}

def get_profile_dir():
    return FIREFOX_COOKIE_JARS[os.name]()

def get_profile_dir_interactive():
    profile_dir = get_profile_dir()

    path = raw_input('Path to firefox profile file [%s]: ' % profile_dir)
    if path.strip():
        # Some input specified, set it
        profile_dir = os.path.realpath(os.path.expanduser(path.strip()))
    return profile_dir

if __name__ == "__main__":
    print get_profile_dir()
