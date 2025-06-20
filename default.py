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
addon = xbmcaddon.Addon('plugin.music.cortanaMPRIS')

# Remote MPRIS host and ports
CMD_PORT = 50506
STATUS_PORT = 50506
DISCOVERY_PORT = 50507
COVER_ART = xbmc.translatePath("Q://UserData//mpris_thumb.jpg")

COMMANDS = [
    ("Stop", "stop"),
    ("Previous", "previous"),
    ("Next", "next"),
    ("Volume +", "volumeup"),
    ("Volume -", "volumedown"),
    ("Refresh", "refresh"),
    ("Notifications", "notifier")
]

def discover_server_ip(timeout=5):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', DISCOVERY_PORT))
        sock.settimeout(timeout)
        xbmc.log("Waiting for UDP broadcast on port %d..." % DISCOVERY_PORT, xbmc.LOGINFO)

        while True:
            data, addr = sock.recvfrom(1024)
            if data.strip() == b"CORTANAMPRIS_HERE":
                xbmc.log("Discovered server at: %s" % addr[0], xbmc.LOGINFO)
                response_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                response_sock.sendto(b"CORTANAMPRIS_FOUND", addr)
                response_sock.close()
                return addr[0]
    except Exception as e:
        xbmc.log("UDP discovery failed: %s" % str(e), xbmc.LOGERROR)
    return None

def get_server_ip():
    ip = addon.getSetting('ip')
    if ip:
        xbmc.log("Using static IP from settings: %s" % ip, xbmc.LOGINFO)
        return ip.strip()
    else:
        xbmc.log("No IP configured, falling back to discovery", xbmc.LOGINFO)
        return discover_server_ip()

HOST = get_server_ip()

def send_command(cmd):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, CMD_PORT))
        s.sendall(cmd.encode('utf-8'))
        s.close()
    except Exception as e:
        msg = "Error: %s" % str(e)
        xbmc.executebuiltin('Notification(cortanaMPRIS, %s, 3000)' % msg)

def fetch_cover_art():
    host = get_server_ip()
    if not host:
        xbmc.log("No server IP available to fetch cover art.", xbmc.LOGERROR)
        return
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((HOST, CMD_PORT))
        s.sendall(b"coverart")
        # Read header (image length)
        header = b''
        while not header.endswith(b'\n'):
            chunk = s.recv(1)
            if not chunk:
                break
            header += chunk
        if not header:
            xbmc.log("No header received for cover art!", xbmc.LOGERROR)
            s.close()
            return
        img_size = int(header.strip())
        img_bytes = b''
        while len(img_bytes) < img_size:
            chunk = s.recv(min(4096, img_size - len(img_bytes)))
            if not chunk:
                break
            img_bytes += chunk
        s.close()
        if img_bytes:
            with open(COVER_ART, 'wb') as f:
                f.write(img_bytes)
            xbmc.log("Fetched cover art (%d bytes)" % img_size, xbmc.LOGINFO)
        else:
            xbmc.log("No cover art bytes received!", xbmc.LOGWARNING)
    except Exception as e:
        xbmc.log("Failed to fetch cover art: %s" % str(e), xbmc.LOGERROR)

def build_playlist():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((HOST, CMD_PORT))
        s.sendall(b"playlist")
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        s.close()
        playlist_lines = data.decode("utf-8").strip().split("\n")
        if not playlist_lines or playlist_lines == ['']:
            xbmcgui.Dialog().ok("Playlist", "No playlist available or unsupported by player.")
            xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
            return

        for line in playlist_lines:
            # Expecting "index|||title"
            if '|||' in line:
                idx, title = line.split('|||', 1)
            else:
                idx, title = str(playlist_lines.index(line)+1), line
            url = sys.argv[0] + '?cmd=jump&idx=%s' % idx
            li = xbmcgui.ListItem(title)
            xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=li, isFolder=False)
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except Exception as e:
        xbmcgui.Dialog().ok("Playlist Error", str(e))
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)

def get_neighbors():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((HOST, CMD_PORT))
        s.sendall(b"tracklist")
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        s.close()
        lines = data.decode('utf-8').split('\n')
        # Expected: previous, current, next
        prev_str, next_str = '', ''
        if len(lines) >= 1 and lines[0].strip():
            prev_parts = lines[0].split('|||')
            if prev_parts and prev_parts[0].strip():
                prev_str = "Previous: %s - %s" % (prev_parts[0], prev_parts[1]) if len(prev_parts) > 1 else "Previous: %s" % prev_parts[0]
        if len(lines) >= 3 and lines[2].strip():
            next_parts = lines[2].split('|||')
            if next_parts and next_parts[0].strip():
                next_str = "Next: %s - %s" % (next_parts[0], next_parts[1]) if len(next_parts) > 1 else "Next: %s" % next_parts[0]
        return prev_str, next_str
    except Exception as e:
        return '', ''

def get_status_line():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((HOST, STATUS_PORT))
        s.sendall(b"status")
        data = s.recv(1024)
        s.close()
        if data:
            return data.decode('utf-8').strip()
    except Exception as e:
        return "Could not get status: " + str(e)
    return "No status available"


def show_playlist():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((HOST, CMD_PORT))
        s.sendall(b"playlist")
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        s.close()
        playlist_lines = data.decode("utf-8").strip().split("\n")
        if not playlist_lines or playlist_lines == ['']:
            xbmcgui.Dialog().ok("Playlist", "No playlist available or unsupported by player.")
            return

        # Present as a selectable dialog
        selected = xbmcgui.Dialog().select("Playlist Queue", playlist_lines)
        if selected >= 0:
            # User selected a track; send jump command
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((HOST, CMD_PORT))
            cmd = "jump:%d" % (selected+1)
            s.sendall(cmd.encode('utf-8'))
            s.close()
    except Exception as e:
        xbmcgui.Dialog().ok("Playlist Error", str(e))

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

        elif cmd in ["next", "previous"]:
            send_command(cmd)

        elif cmd == "refresh":
            xbmc.executebuiltin('Container.Refresh')

        elif cmd == "volumeup":
            send_command(cmd)

        elif cmd == "volumedown":
            send_command(cmd)

        elif cmd == "notifier":
            start_notifier()

        elif cmd == "playlist":
            build_playlist()
        elif cmd == "jump" and 'idx' in params:
            idx = params['idx']
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((HOST, CMD_PORT))
            cmdstr = "jump:%s" % idx
            s.sendall(cmdstr.encode('utf-8'))
            s.close()
            xbmc.executebuiltin('Container.Refresh')
        else:
            send_command(cmd)

def build_list():
    fetch_cover_art()
    status_line = get_status_line()
    toggle_url = sys.argv[0] + '?cmd=toggle'

    li = xbmcgui.ListItem(status_line)
    if os.path.isfile(COVER_ART):
        li.setThumbnailImage(COVER_ART)

    li.setInfo(type='music', infoLabels={"title": status_line})
    xbmcplugin.addDirectoryItem(handle=handle, url=toggle_url, listitem=li, isFolder=True)

    for label, cmd in COMMANDS:
        url = sys.argv[0] + '?cmd=' + urllib.quote(cmd)
        li = xbmcgui.ListItem(label)
        xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=li, isFolder=True)

    # Disable caching here
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
            time.sleep(3)
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
