import asyncio
import json

import websockets
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton

VTS_WS_URL = "ws://localhost:8001"  # WebSocket URL for VTube Studio API

class VTubeConnectionThread(QThread):
    status_update = pyqtSignal(str)
    connection_status = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = True
        self.auth_token = None
        self.websocket = None

    async def request_token(self):
        async with websockets.connect(VTS_WS_URL) as websocket:
            token_request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "preflight",
                "messageType": "AuthenticationTokenRequest",
                "data": {
                    "pluginName": "Lily III",
                    "pluginDeveloper": "NsTut",
                }
            }
            await websocket.send(json.dumps(token_request))
            response = await websocket.recv()
            response_data = json.loads(response)["data"]
            return response_data["authenticationToken"]

    async def authenticate_with_vtube_studio(self, websocket, auth_token):
        auth_request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "auth",
            "messageType": "AuthenticationRequest",
            "data": {
                "pluginName": "Lily III",
                "pluginDeveloper": "NsTut",
                "authenticationToken": auth_token,
            }
        }
        await websocket.send(json.dumps(auth_request))
        response = await websocket.recv()
        response_data = json.loads(response)["data"]
        if response_data["authenticated"]:
            self.status_update.emit("Connected")
            self.connection_status.emit(True)
        else:
            self.status_update.emit(f"Authentication Failed: {response_data['reason']}")
            self.connection_status.emit(False)

    async def run_connection(self):
        try:
            self.status_update.emit("Connecting")
            self.auth_token = await self.request_token()
            self.websocket = await websockets.connect(VTS_WS_URL)
            await self.authenticate_with_vtube_studio(self.websocket, self.auth_token)

            # Keep the WebSocket open until stopped
            while self.is_running:
                await asyncio.sleep(1)
        except Exception as e:
            self.status_update.emit(f"Error: {e}")
            self.connection_status.emit(False)

    async def close_connection(self):
        """Gracefully closes the WebSocket connection."""
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
            self.status_update.emit("Not Connected")
            self.connection_status.emit(False)

    def run(self):
        asyncio.run(self.run_connection())

    def stop(self):
        """Stops the thread and closes the WebSocket."""
        self.is_running = False
        if self.websocket and not self.websocket.closed:
            asyncio.run(self.close_connection())


class VTubeTab(QWidget):
    def __init__(self):
        super().__init__()
        self.is_connected = False
        self.connection_thread = None

        self.status_label = QLabel("Not Connected", self)
        self.status_label.setAlignment(Qt.AlignCenter)

        self.connect_button = QPushButton("Connect", self)
        self.connect_button.clicked.connect(self.on_connect_button_clicked)
        self.connect_button.setStyleSheet("width: 200px; height: 40px;")

        layout = QVBoxLayout()
        layout.addWidget(self.connect_button)
        layout.addWidget(self.status_label)
        layout.setAlignment(Qt.AlignCenter)

        self.setLayout(layout)

    def on_connect_button_clicked(self):
        if not self.is_connected:
            self.connect_to_vtube_studio()
        else:
            self.disconnect_from_vtube_studio()

    def connect_to_vtube_studio(self):
        self.update_status("Connecting")
        self.connect_button.setEnabled(False)

        self.connection_thread = VTubeConnectionThread(self)
        self.connection_thread.status_update.connect(self.update_status)
        self.connection_thread.connection_status.connect(self.update_connection_status)
        self.connection_thread.start()

    def disconnect_from_vtube_studio(self):
        if self.connection_thread:
            self.connection_thread.stop()
            self.connection_thread.wait()  # Wait for the thread to finish
        self.update_status("Not Connected")
        self.is_connected = False
        self.update_button_text()

    def update_status(self, status):
        self.status_label.setText(status)

    def update_connection_status(self, connected):
        self.is_connected = connected
        self.update_button_text()
        self.connect_button.setEnabled(True)

    def update_button_text(self):
        self.connect_button.setText("Disconnect" if self.is_connected else "Connect")
