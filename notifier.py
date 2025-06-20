# -*- coding: utf-8 -*-
import xbmc
import socket
import os
import time

HOST = '192.168.1.110'
PORT = 50506
CHECK_INTERVAL = 5  # seconds between checks
COVER_ART = xbmc.translatePath("Q://UserData//mpris_notify.jpg")

def get_status_line():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((HOST, PORT))
        s.sendall(b"status")
        data = s.recv(1024)
        s.close()
        if data:
            return unicode(data, 'utf-8').strip()
    except Exception as e:
        xbmc.log("notifier.py: Could not get status: %s" % str(e), xbmc.LOGERROR)
    return None

def show_notification(status_line, icon_path):
    try:
        if not isinstance(status_line, unicode):
            status_line = unicode(status_line, 'utf-8')
        encoded_status = status_line.encode('utf-8')
        xbmc.executebuiltin(
            'Notification(cortanaMPRIS, %s, 3500, %s)' % (encoded_status, icon_path)
        )
    except Exception as e:
        xbmc.log("Notifier: Could not show notification: %s" % str(e), xbmc.LOGERROR)

def fetch_cover_art():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((HOST, PORT))
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

def main():
    last_status = ""
    try:
        while True:
            status_line = get_status_line()
            if status_line and status_line != last_status:
                fetch_cover_art()
                icon_path = COVER_ART if os.path.isfile(COVER_ART) else ""
                show_notification(status_line, icon_path)
                last_status = status_line
            xbmc.sleep(CHECK_INTERVAL * 1000)
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
