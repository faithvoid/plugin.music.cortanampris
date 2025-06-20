import xbmc
import socket
import os
import time
import xml.etree.ElementTree as ET

PORT = 50506
CHECK_INTERVAL = 5
DISCOVERY_PORT = 50507
COVER_ART = xbmc.translatePath("Z://temp//mpris_notify.jpg")

HOST = None
lost_connection = False

def get_configured_ip():
    settings_path = xbmc.translatePath("special://profile/addon_data/plugin.music.cortanaMPRIS/settings.xml")
    try:
        tree = ET.parse(settings_path)
        root = tree.getroot()
        for setting in root.findall('setting'):
            if setting.attrib.get('id') == 'ip':
                return setting.attrib.get('value', '').strip()
    except Exception as e:
        xbmc.log("Failed to read settings.xml: %s" % str(e), xbmc.LOGERROR)
    return None

def discover_server():
    global HOST
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', DISCOVERY_PORT))
        sock.settimeout(5)

        while True:
            data, addr = sock.recvfrom(1024)
            if data.strip() == b"CORTANAMPRIS_HERE":
                xbmc.log("Received broadcast from %s" % addr[0], xbmc.LOGINFO)
                HOST = addr[0]
                response_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                response_sock.sendto(b"CORTANAMPRIS_FOUND", addr)
                response_sock.close()
                break

    except Exception as e:
        xbmc.log("Discovery failed: %s" % str(e), xbmc.LOGERROR)

def get_status_line():
    global lost_connection
    if not HOST:
        return None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((HOST, PORT))
        s.sendall(b"status")
        data = s.recv(1024)
        s.close()
        lost_connection = False
        return unicode(data, 'utf-8').strip() if data else None
    except Exception:
        if not lost_connection:
            xbmc.executebuiltin('Notification(cortanaMPRIS, "Lost connection to MPRIS device", 5000)')
            lost_connection = True
        return None

def fetch_cover_art():
    if not HOST:
        return
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((HOST, PORT))
        s.sendall(b"coverart")

        header = b''
        while not header.endswith(b'\n'):
            chunk = s.recv(1)
            if not chunk:
                break
            header += chunk

        if not header:
            s.close()
            return

        img_size = int(header.strip())
        img_bytes = b''
        while len(img_bytes) < img_size:
            img_bytes += s.recv(min(4096, img_size - len(img_bytes)))
        s.close()

        if img_bytes:
            with open(COVER_ART, 'wb') as f:
                f.write(img_bytes)

    except Exception as e:
        xbmc.log("Cover fetch failed: %s" % str(e), xbmc.LOGERROR)

def show_notification(status_line, icon_path):
    try:
        if not isinstance(status_line, unicode):
            status_line = unicode(status_line, 'utf-8')
        xbmc.executebuiltin('Notification(cortanaMPRIS, %s, 3500, %s)' % (status_line.encode('utf-8'), icon_path))
    except Exception as e:
        xbmc.log("Notification failed: %s" % str(e), xbmc.LOGERROR)

def main():
    global HOST
    last_status = ""

    # Use configured IP if set, otherwise fall back to discovery
    HOST = get_configured_ip()
    if HOST:
        xbmc.log("Using static IP from addon settings: %s" % HOST, xbmc.LOGINFO)
    else:
        xbmc.log("No static IP configured. Starting discovery...", xbmc.LOGINFO)
        discover_server()

    if not HOST:
        xbmc.log("Could not find MPRIS server.", xbmc.LOGERROR)
        return

    while True:
        status_line = get_status_line()
        if status_line and status_line != last_status:
            fetch_cover_art()
            icon_path = COVER_ART if os.path.isfile(COVER_ART) else ""
            show_notification(status_line, icon_path)
            last_status = status_line
        xbmc.sleep(CHECK_INTERVAL * 1000)

if __name__ == '__main__':
    main()
