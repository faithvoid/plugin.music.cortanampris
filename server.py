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

RECEIVER = '0.0.0.0'
RCV_PORT = 50506

pause_timer = None
pause_data = None
lock = threading.Lock()

last_track_info = {
    'title': '',
    'artist': '',
    'album': '',
    'year': '',
    'status': '',  # "Playing", "Paused", or other
}

def format_track_info(title, artist, album, year):
    if album and year:
        return f"{title} - {artist} ({album}, {year})"
    elif album:
        return f"{title} - {artist} ({album})"
    else:
        return f"{title} - {artist}"

def get_mpris_player():
    session_bus = dbus.SessionBus()
    players = [s for s in session_bus.list_names() if s.startswith("org.mpris.MediaPlayer2.")]
    if not players:
        return None, None
    try:
        player = session_bus.get_object(players[0], "/org/mpris/MediaPlayer2")
        iface = dbus.Interface(player, "org.mpris.MediaPlayer2.Player")
        props = dbus.Interface(player, "org.freedesktop.DBus.Properties")
        props.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus")
        return iface, props
    except dbus.exceptions.DBusException:
        return None, None

def get_status_line():
    with lock:
        status = last_track_info['status']
        title = last_track_info['title']
        artist = last_track_info['artist']
        album = last_track_info.get('album', '')
        year = last_track_info.get('year', '')
    info_str = format_track_info(title, artist, album, year)
    status_lower = status.lower()
    if status_lower == "playing":
        return f"Playing: {info_str}"
    elif status_lower == "paused":
        return f"Paused: {info_str}"
    else:
        return f"{status}: {info_str}"

def resize_image_bytes(image_bytes, size=(256, 256)):
    try:
        with io.BytesIO(image_bytes) as input_buffer:
            with Image.open(input_buffer) as img:
                img = img.convert('RGB')
                img.thumbnail(size, Image.LANCZOS)
                with io.BytesIO() as output_buffer:
                    img.save(output_buffer, format='JPEG')
                    return output_buffer.getvalue()
    except Exception as e:
        print("Failed to resize image:", e)
        return image_bytes

def toggle_play_pause():
    with lock:
        status = last_track_info['status']
    cmd = "pause" if status.lower() == "playing" else "play"
    receive_from_xbmc(cmd)

def combined_status_command_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((RECEIVER, RCV_PORT))
    server.listen(5)
    print("Listening for XBMC commands and status requests on port %d..." % RCV_PORT)
    
    while True:
        client, addr = server.accept()
        with client:
            try:
                data = client.recv(1024)
                if not data:
                    line = get_status_line()
                    client.sendall(line.encode('utf-8'))
                else:
                    command = data.decode('utf-8').strip().lower()
                    if command == "status":
                        line = get_status_line()
                        client.sendall(line.encode('utf-8'))
                    elif command == "coverart":
                        now_playing = get_now_playing()
                        image = resize_image_bytes(now_playing.get('image_bytes', b'')) if now_playing and now_playing.get('image_bytes') else b''
                        header = str(len(image)).encode('utf-8') + b'\n'
                        client.sendall(header)
                        if image:
                            client.sendall(image)
                    elif command == "tracklist":
                        prev_md, cur_md, next_md = get_track_neighbors()
                        def md_to_line(md):
                            if not md:
                                return ""
                            title = md.get("xesam:title", "")
                            artist = md.get("xesam:artist", [""])[0] if md.get("xesam:artist") else ""
                            album = md.get("xesam:album", "")
                            return "%s|||%s|||%s" % (title, artist, album)
                        response = {
                            'previous': md_to_line(prev_md),
                            'current': md_to_line(cur_md),
                            'next': md_to_line(next_md),
                        }
                        lines = [response['previous'], response['current'], response['next']]
                        client.sendall("\n".join(lines).encode('utf-8'))
                    elif command == "playlist":
                        playlist = get_playlist()
                        if not playlist:
                            response = "Playlist/queue not available or not supported by player."
                        else:
                            response = "\n".join(["%d|||%s" % (i+1, entry[1]) for i, entry in enumerate(playlist)])
                        client.sendall(response.encode('utf-8'))
                    elif command.startswith("jump:"):
                        try:
                            index = int(command.split(":", 1)[1])
                            result = jump_to_track(index)
                            if result is not None:
                                client.sendall(str(result).encode('utf-8'))
                            else:
                                client.sendall(b"OK")
                        except Exception as e:
                            client.sendall(("Error: %s" % str(e)).encode('utf-8'))
                    else:
                        receive_from_xbmc(command)
                        client.sendall(b"OK")
            except Exception as e:
                print("Error handling client:", e)

def get_now_playing():
    iface, props = get_mpris_player()
    if not props:
        return None

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
            try:
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()
            except Exception as e:
                print("Failed to read art file:", e)
    elif art_url.startswith("http"):
        try:
            r = requests.get(art_url, timeout=3)
            if r.ok:
                image_bytes = r.content
        except requests.RequestException as e:
            print("Failed to fetch art URL:", e)

    return {
        'title': title,
        'artist': artist,
        'album': album,
        'year': year,
        'image_bytes': image_bytes,
        'playback_status': playback_status,
    }

def get_playlist():
    iface, props = get_mpris_player()
    if not props:
        return []
    try:
        pl_iface = dbus.Interface(iface, "org.mpris.MediaPlayer2.Playlists")
        playlists = pl_iface.GetPlaylists(0, 100, "User")
        return playlists
    except Exception as e:
        print("Failed to get playlist:", e)
        return []

def get_track_neighbors():
    session_bus = dbus.SessionBus()
    players = [s for s in session_bus.list_names() if s.startswith("org.mpris.MediaPlayer2.")]
    if not players:
        return None, None, None

    player = session_bus.get_object(players[0], "/org/mpris/MediaPlayer2")
    props = dbus.Interface(player, "org.freedesktop.DBus.Properties")

    try:
        cur_track_id = props.Get("org.mpris.MediaPlayer2.Player", "Metadata").get("mpris:trackid")
    except Exception:
        cur_track_id = None

    try:
        tracklist_iface = dbus.Interface(player, "org.mpris.MediaPlayer2.TrackList")
        track_ids = tracklist_iface.GetTracks()
    except Exception as e:
        print("Failed to get tracklist via TrackList interface:", e)
        return None, None, None

    all_metadata = []
    for tid in track_ids:
        try:
            md = props.Get("org.mpris.MediaPlayer2.TrackList", "Metadata", tid)
            all_metadata.append(md)
        except Exception:
            all_metadata.append({'mpris:trackid': tid})

    idx = None
    for i, md in enumerate(all_metadata):
        if md.get('mpris:trackid') == cur_track_id:
            idx = i
            break

    prev_md, cur_md, next_md = None, None, None
    if idx is not None:
        cur_md = all_metadata[idx]
        if idx > 0:
            prev_md = all_metadata[idx - 1]
        if idx < len(all_metadata) - 1:
            next_md = all_metadata[idx + 1]

    return prev_md, cur_md, next_md

def jump_to_track(index):
    iface, props = get_mpris_player()
    if not iface:
        return "No player found"
    try:
        print("Attempting to jump to track %d" % index)
        return None
    except Exception as e:
        print("Failed to jump to track:", e)
        return "Failed to jump: %s" % str(e)

def receive_from_xbmc(command):
    iface, _ = get_mpris_player()
    if not iface:
        print("No MPRIS player found")
        return

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

def notify_pause():
    global pause_data, lock
    with lock:
        pause_data = None

if __name__ == '__main__':
    combined_thread = threading.Thread(target=combined_status_command_server, daemon=True)
    combined_thread.start()

    last_data = None
    last_status = None
    while True:
        now_playing = get_now_playing()
        if now_playing and now_playing != last_data:
            status = now_playing['playback_status']
            with lock:
                last_track_info['title'] = now_playing['title']
                last_track_info['artist'] = now_playing['artist']
                last_track_info['album'] = now_playing['album']
                last_track_info['year'] = now_playing['year']
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
            last_data = now_playing
            last_status = status
        time.sleep(0.2)
