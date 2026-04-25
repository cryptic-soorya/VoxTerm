# Custom hook to override the contrib hook-webrtcvad.py.
# The package is installed as `webrtcvad-wheels`, not `webrtcvad`,
# so copy_metadata('webrtcvad') fails. We copy the wheels metadata instead.
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("webrtcvad-wheels")
