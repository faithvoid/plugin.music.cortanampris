# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcplugin
import sys
import socket
import urllib
import os
import time
import xml.etree.ElementTree as ET
import subprocess
import xbmcaddon

# Plugin handle
handle = int(sys.argv[1])
addon = xbmcaddon.Addon()

# Remote MPRIS host and ports
HOST = '192.168.1.110'
CMD_PORT = 50506
STATUS_PORT = 50506
COVER_ART = xbmc.translatePath("special://temp/mpris.jpg")

COMMANDS = [
    ("Stop", "stop"),
    ("Previous", "previous"),
    ("Next", "next"),
    ("Refresh", "refresh"),
    ("Notifications", "notifier")
]

def send_command(cmd):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, CMD_PORT))
        s.sendall(cmd.encode('utf-8'))
        s.close()
    except Exception as e:
        msg = "Error: %s" % str(e)
        xbmc.executebuiltin('Notification(cortanaMPRIS, %s, 3000)' % msg)

def get_status_line():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((HOST, STATUS_PORT))
        s.sendall(b"status")   # <-- send "status" request immediately
        data = s.recv(1024)
        s.close()
        if data:
            status = data.decode('utf-8').strip()
            if status.lower().startswith("paused"):
                # Wait a moment and check again
                time.sleep(3)
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(3)
                    s.connect((HOST, STATUS_PORT))
                    s.sendall(b"status")  # send again
                    data2 = s.recv(1024)
                    s.close()
                    if data2:
                        second_status = data2.decode('utf-8').strip()
                        if second_status.lower().startswith("playing"):
                            return second_status
                except:
                    pass  # fallback to original status
            return status
    except Exception as e:
        return "Could not get status: " + str(e)
    return "No status available"



def router(paramstring):
    params = dict(part.split('=') for part in paramstring[1:].split('&') if '=' in part)
    if 'cmd' in params:
        cmd = params['cmd']

        if cmd == "toggle":
            status = get_status_line().lower()
            if status.startswith("playing"):
                send_command("pause")
            else:
                send_command("play")
            time.sleep(0.5)
            xbmc.executebuiltin('Container.Refresh')

        elif cmd in ["next", "previous"]:
            send_command(cmd)
            time.sleep(0.5)
            xbmc.executebuiltin('Container.Refresh')

        elif cmd == "refresh":
            xbmc.executebuiltin('Container.Refresh')

        elif cmd == "notifier":
            start_notifier()

        else:
            send_command(cmd)

def build_list():
    status_line = get_status_line()
    toggle_url = sys.argv[0] + '?cmd=toggle'

    li = xbmcgui.ListItem(status_line)
    
    if os.path.isfile(COVER_ART):
        li.setThumbnailImage(COVER_ART)

    li.setInfo(type='music', infoLabels={"title": status_line})
    xbmcplugin.addDirectoryItem(handle=handle, url=toggle_url, listitem=li, isFolder=False)

    for label, cmd in COMMANDS:
        url = sys.argv[0] + '?cmd=' + urllib.quote(cmd)
        li = xbmcgui.ListItem(label)
        xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=li, isFolder=False)

    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)

def read_notifier_startup():
    try:
        val = addon.getSetting("notifier_startup").lower()
        xbmc.log("Notifier startup setting read as: %s" % val, xbmc.LOGINFO)
        return val == 'true'
    except Exception as e:
        xbmc.log("Failed to read notifier_startup setting: %s" % e, xbmc.LOGERROR)
        return False

def start_notifier():
    folder = os.path.dirname(os.path.abspath(__file__))
    notifier_path = os.path.join(folder, 'notifier.py')
    if os.path.isfile(notifier_path):
        try:
            xbmc.executebuiltin('RunScript("%s")' % notifier_path)
            xbmc.log("Started notifier.py using RunScript", xbmc.LOGINFO)
        except Exception as e:
            xbmc.log("Failed to start notifier.py: %s" % e, xbmc.LOGERROR)
    else:
        xbmc.log("notifier.py not found!", xbmc.LOGERROR)


if __name__ == '__main__':
    if read_notifier_startup():
        start_notifier()

    if '?' in sys.argv[2]:
        if '_refresh=' in sys.argv[2]:
            build_list()
        else:
            router(sys.argv[2])
    else:
        build_list()
