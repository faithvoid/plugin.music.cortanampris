# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcplugin
import sys
import socket
import urllib
import os
import time

# Plugin handle
handle = int(sys.argv[1])

# Remote MPRIS host and ports
HOST = '192.168.1.110'  # Your Linux host IP running MPRIS bridge
CMD_PORT = 50506        # Command listener port
STATUS_PORT = 50507     # Status server port
COVER_ART = xbmc.translatePath("special://temp/mpris.jpg")

COMMANDS = [
    ("Stop", "stop"),
    ("Previous", "previous"),
    ("Next", "next"),
]

def send_command(cmd):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, CMD_PORT))
        s.sendall(cmd.encode('utf-8'))
        s.close()
    except Exception as e:
        msg = "Error: %s" % str(e)
        xbmc.executebuiltin('Notification(MPRIS, %s, 3000)' % msg)

def get_status_line():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((HOST, STATUS_PORT))
        data = s.recv(1024)
        s.close()
        if data:
            status = data.decode('utf-8').strip()
            if status.lower().startswith("paused"):
                # Wait a moment and check again
                time.sleep(3)
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2)
                    s.connect((HOST, STATUS_PORT))
                    data2 = s.recv(1024)
                    s.close()
                    if data2:
                        second_status = data2.decode('utf-8').strip()
                        if second_status.lower().startswith("playing"):
                            return second_status
                except:
                    pass  # If retry fails, fall back to original status
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

    # Disable caching here
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


if __name__ == '__main__':
    if '?' in sys.argv[2]:
        if '_refresh=' in sys.argv[2]:
            build_list()
        else:
            router(sys.argv[2])
    else:
        build_list()

