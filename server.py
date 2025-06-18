# -*- coding: utf-8 -*-
import dbus
import socket
import time
import os
import threading
from urllib.parse import urlparse
import requests

HOST = '192.168.1.105'
PORT = 50505

pause_timer = None
pause_data = None
lock = threading.Lock()

def get_now_playing():
    session_bus = dbus.SessionBus()
    mpris_players = [s for s in session_bus.list_names() if s.startswith("org.mpris.MediaPlayer2.")]
    if not mpris_players:
        return None

    player = session_bus.get_object(mpris_players[0], "/org/mpris/MediaPlayer2")
    props = dbus.Interface(player, "org.freedesktop.DBus.Properties")
    
    playback_status = props.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus")
    metadata = props.Get("org.mpris.MediaPlayer2.Player", "Metadata")

    title = metadata.get("xesam:title", "Unknown Title")
    artist = metadata.get("xesam:artist", ["Unknown Artist"])[0]
    album = metadata.get("xesam:album", "Unknown Album")

    year_raw = metadata.get("xesam:contentCreated", "")
    if isinstance(year_raw, dbus.String):
        year_raw = str(year_raw)
    year = year_raw[:4] if len(year_raw) >= 4 and year_raw[:4].isdigit() else ""

    art_url = metadata.get("mpris:artUrl", "")

    image_bytes = b""
    if art_url.startswith("file://"):
        image_path = urlparse(art_url).path
        if os.path.isfile(image_path):
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
    elif art_url.startswith("http"):
        try:
            r = requests.get(art_url, timeout=3)
            if r.ok:
                image_bytes = r.content
        except:
            pass

    return {
        'title': title,
        'artist': artist,
        'album': album,
        'year': year,
        'image_bytes': image_bytes,
        'playback_status': playback_status,
    }

def send_to_xbmc(data):
    try:
        title = data['title']
        artist = data['artist']
        album = data['album']
        year = data['year']
        image = data['image_bytes']
        status = data['playback_status']
        header = u"{}|||{}|||{}|||{}|||{}|||{}".format(
            title, artist, album, year, len(image), status
        ).encode('utf-8')

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, PORT))
        s.sendall(header + b'\n')
        if image:
            s.sendall(image)
        s.close()
        print("Sent:", title, artist, status)
    except Exception as e:
        print("Failed to send:", e)

def notify_pause():
    global pause_data, lock
    with lock:
        if pause_data:
            send_to_xbmc(pause_data)
            pause_data = None

if __name__ == '__main__':
    last_data = None
    last_status = None
    while True:
        now_playing = get_now_playing()
        if now_playing and now_playing != last_data:
            status = now_playing['playback_status']
            if status == "Paused":
                with lock:
                    if pause_timer and pause_timer.is_alive():
                        pause_timer.cancel()
                    pause_data = now_playing
                    pause_timer = threading.Timer(3.0, notify_pause)
                    pause_timer.start()
            elif status == "Playing":
                with lock:
                    if pause_timer and pause_timer.is_alive():
                        pause_timer.cancel()
                        pause_data = None
                send_to_xbmc(now_playing)
            else:
                send_to_xbmc(now_playing)
            last_data = now_playing
            last_status = status
        time.sleep(0.2)
