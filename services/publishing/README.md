OAuth, encrypted tokens and resumable official YouTube uploads: `services/api/xek/publishing.py`.
The `youtube.upload` scope uploads videos; `youtube.readonly` identifies the connected channel name.
Publishing is off by default. Failed uploads are blocked from blind retry to avoid duplicates.
