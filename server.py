# -*- coding: utf-8 -*-
import dbus
import socket
import time
import os
import threading
from urllib.parse import urlparse
import requests
from PIL import Image
import io

HOST = '192.168.1.105'
PORT = 50505

RCV_HOST = '0.0.0.0'
RCV_PORT = 50506

STATUS_SERVER_HOST = '0.0.0.0'
STATUS_SERVER_PORT = 50507

pause_timer = None
pause_data = None
lock = threading.Lock()

last_track_info = {
    'title': '',
    'artist': '',
    'status': '',  # "Playing", "Paused", or other
}

def get_status_line():
    with lock:
        status = last_track_info['status']
        title = last_track_info['title']
        artist = last_track_info['artist']
    if status.lower() == "playing":
        return f"Playing: {title} - {artist}"
    elif status.lower() == "paused":
        return f"Paused: {title} - {artist}"
    else:
        return f"{status}: {title} - {artist}"

def resize_image_bytes(image_bytes, size=(256, 256)):
    try:
        with io.BytesIO(image_bytes) as input_buffer:
            with Image.open(input_buffer) as img:
                img = img.convert('RGBA')
                img.thumbnail(size, Image.LANCZOS)
                with io.BytesIO() as output_buffer:
                    img.save(output_buffer, format='PNG')
                    return output_buffer.getvalue()
    except Exception as e:
        print("Failed to resize image:", e)
        return image_bytes  # fallback to original bytes if resize fails


def toggle_play_pause():
    with lock:
        status = last_track_info['status']
    if status.lower() == "playing":
        receive_from_xbmc("pause")
    else:
        receive_from_xbmc("play")

def status_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((STATUS_SERVER_HOST, STATUS_SERVER_PORT))
    server.listen(5)
    print(f"Status server listening on port {STATUS_SERVER_PORT}...")
    while True:
        client, addr = server.accept()
        with client:
            # Just send the current status line and close
            line = get_status_line()
            client.sendall(line.encode('utf-8'))

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
        image = resize_image_bytes(data['image_bytes']) if data['image_bytes'] else b""
        print(f"Original image bytes: {len(data['image_bytes'])}, Resized image bytes: {len(image)}")
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

def receive_from_xbmc(command):
    session_bus = dbus.SessionBus()
    mpris_players = [s for s in session_bus.list_names() if s.startswith("org.mpris.MediaPlayer2.")]
    if not mpris_players:
        print("No MPRIS player found")
        return

    player = session_bus.get_object(mpris_players[0], "/org/mpris/MediaPlayer2")
    iface = dbus.Interface(player, "org.mpris.MediaPlayer2.Player")

    command = command.strip().lower()
    try:
        if command == "play":
            iface.Play()
        elif command == "pause":
            iface.Pause()
        elif command == "stop":
            iface.Stop()
        elif command == "previous":
            iface.Previous()
        elif command == "next":
            iface.Next()
        else:
            print(f"Unknown command: {command}")
            return
        print(f"Executed MPRIS command: {command}")
    except Exception as e:
        print(f"Failed to send command '{command}':", e)

def xbmc_command_listener():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((RCV_HOST, RCV_PORT))  # Match PORT in XBMC add-on
    server.listen(5)
    print("Listening for XBMC commands on port 50506...")
    
    while True:
        client, addr = server.accept()
        with client:
            data = client.recv(1024)
            if data:
                command = data.decode('utf-8').strip()
                receive_from_xbmc(command)

def notify_pause():
    global pause_data, lock
    with lock:
        if pause_data:
            send_to_xbmc(pause_data)
            pause_data = None

if __name__ == '__main__':
    # Start the command listener thread (port 50506)
    listener_thread = threading.Thread(target=xbmc_command_listener, daemon=True)
    listener_thread.start()

    # Start the status server thread (port 50507)
    status_thread = threading.Thread(target=status_server, daemon=True)
    status_thread.start()

    last_data = None
    last_status = None
    while True:
        now_playing = get_now_playing()
        if now_playing and now_playing != last_data:
            status = now_playing['playback_status']
            with lock:
                last_track_info['title'] = now_playing['title']
                last_track_info['artist'] = now_playing['artist']
                last_track_info['status'] = status

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
