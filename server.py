import dbus
import socket
import time
import os
from urllib.parse import urlparse
import requests

HOST = '192.168.1.105'
PORT = 50505

def get_now_playing():
    session_bus = dbus.SessionBus()
    mpris_players = [s for s in session_bus.list_names() if s.startswith("org.mpris.MediaPlayer2.")]
    if not mpris_players:
        return None

    player = session_bus.get_object(mpris_players[0], "/org/mpris/MediaPlayer2")
    props = dbus.Interface(player, "org.freedesktop.DBus.Properties")
    
    playback_status = props.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus")  # New
    
    metadata = props.Get("org.mpris.MediaPlayer2.Player", "Metadata")

    title = metadata.get("xesam:title", "Unknown Title")
    artist = metadata.get("xesam:artist", ["Unknown Artist"])[0]
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
        'image_bytes': image_bytes,
        'playback_status': playback_status,  # New
    }

def send_to_xbmc(data):
    try:
        title = data['title']
        artist = data['artist']
        image = data['image_bytes']
        status = data['playback_status']

        header = "{}|||{}|||{}|||{}".format(title, artist, len(image), status).encode('utf-8')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            s.sendall(header + b'\n')  # header is line-delimited
            if image:
                s.sendall(image)
    except Exception as e:
        print("Failed to send:", e)

if __name__ == '__main__':
    last_data = None
    while True:
        now_playing = get_now_playing()
        if now_playing and now_playing != last_data:
            send_to_xbmc(now_playing)
            last_data = now_playing
        time.sleep(1)
