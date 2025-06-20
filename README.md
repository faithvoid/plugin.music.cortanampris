# cortanaMPRIS
### MPRIS media notification + control utility for XBMC4Xbox

![](screenshots/menu.jpg)
![](screenshots/1.jpg)
![](screenshots/2.jpg)

## How to Use:
- Download the latest release .zip
- Copy the "cortanaMPRIS" folder to "Q:/plugins/music/"
- Copy "server.py" anywhere on your system, make sure ports 50506 and 50507 are open on your host machine, then run the server with "python server.py" (this is currently only for Linux users, sorry!). Requires the requests & pillow Python libraries.
- Run the server, then launch the add-on and you should automatically be connected! If that doesn't work, you can go into the add-on settings in XBMC via the context menu and manually specify an IP address to connect to.
- (Optional) To enable notifications, select "Notification" in the main menu (or run Q:/plugins/music/cortanaMPRIS/notifier.py), then listen to a track on your system and watch as a notification pops up with the full track information and cover art!

## FAQ:
- "It's not working for some reason?"
- Check that ports 50506 and 50507 are both open on your host machine! If they are and it's still not working, enter your IP address manually in the plugin settings and try again.
- "When I launch the notification script, the MPRIS control add-on stops connecting / showing title + cover information / etc."
- This shouldn't happen anymore, but if it does, please let me know. There's a socket issue that sometimes janks things up if the notification script and the control add-on are launched too close together.
- "Will this come to XYZ operating system?"
- Nope, MPRIS is Linux-only (there are BSD ports but they're untested afaik). Feel free to make a fork with your own compatible audio control libraries though.

## Bugs:
- "Pause" is a bit slow due to having to work around a play/pause flicker issue with web apps like Spotify.
