import socket
import xbmc
import time

HOST = '0.0.0.0'
PORT = 50505
title_str = "cortanaMPRIS"

def show_notification(title, message, image=None):
    if image:
        xbmc.executebuiltin('Notification("%s", "%s", 5000, "%s")' % (title, message, image))
    else:
        xbmc.executebuiltin('Notification("%s", "%s", 5000)' % (title, message))

def start_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(1)
    xbmc.executebuiltin('Notification("cortanaMPRIS", "cortanaMPRIS online!", 5000)')

    while True:
        conn, addr = s.accept()
        try:
            header = b""
            while not header.endswith(b'\n'):
                chunk = conn.recv(1)
                if not chunk:
                    break
                header += chunk

            parts = header.strip().decode('utf-8').split("|||")
            if len(parts) != 4:
                continue
            title, artist, length_str, playback_status = parts
            image_len = int(length_str)

            image_data = b''
            while len(image_data) < image_len:
                chunk = conn.recv(min(1024, image_len - len(image_data)))
                if not chunk:
                    break
                image_data += chunk

            if image_data:
                filename = "cover_%d.jpg" % int(time.time()*1000)
                image_path = xbmc.translatePath("special://temp/%s" % filename)
                with open(image_path, 'wb') as f:
                    f.write(image_data)
                    f.flush()
                time.sleep(0.2)
            else:
                image_path = None

            # Build message based on playback status
            if playback_status == "Playing":
                msg = u"Playing: %s - %s" % (artist, title)
            elif playback_status == "Paused":
                msg = u"Paused: %s - %s" % (artist, title)
            elif playback_status == "Stopped":
                msg = u"Playback stopped."
            else:
                msg = u"%s - %s" % (artist, title)

            show_notification(title_str, msg, image_path)

        except Exception as e:
            xbmc.log("Error in MPRIS handler: %s" % str(e), xbmc.LOGERROR)
        finally:
            conn.close()

if __name__ == "__main__":
    start_server()
