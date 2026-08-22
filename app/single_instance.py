"""Per-user single-instance coordination using Qt local IPC."""
from __future__ import annotations

import getpass
import hashlib
import json
import logging
import os
from pathlib import Path
import struct
import sys
from typing import Callable

from PySide6.QtCore import QObject, QStandardPaths, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

LOG=logging.getLogger(__name__)
PROTOCOL_VERSION=1
MAX_MESSAGE_BYTES=1024*1024
CONNECT_TIMEOUT_MS=180
RETRY_COUNT=5
SUPPORTED_FILE_SUFFIXES={".diamond",".jpg",".jpeg",".png",".webp",".bmp"}


def _user_identity_seed():
    app_data=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    return f"{getpass.getuser()}|{Path.home()}|{app_data}|{os.name}"


def instance_server_name(identity=None):
    digest=hashlib.sha256((identity or _user_identity_seed()).encode("utf-8","surrogatepass")).hexdigest()[:20]
    return f"Drillbit_{digest}"


def activation_payload(files=()):
    return {"version":PROTOCOL_VERSION,"action":"activate","files":[str(Path(path).resolve()) for path in files]}


def encode_payload(payload):
    body=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    if len(body)>MAX_MESSAGE_BYTES:raise ValueError("IPC activation request is too large.")
    return struct.pack(">I",len(body))+body


def decode_payload(body):
    try:payload=json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError):return None
    if not isinstance(payload,dict) or payload.get("version")!=PROTOCOL_VERSION or payload.get("action")!="activate":return None
    files=payload.get("files",[])
    if not isinstance(files,list) or any(not isinstance(path,str) for path in files):return None
    return {"version":PROTOCOL_VERSION,"action":"activate","files":files}


def extract_frames(buffer):
    frames=[]
    while len(buffer)>=4:
        length=struct.unpack(">I",buffer[:4])[0]
        if length>MAX_MESSAGE_BYTES:raise ValueError("IPC activation request is too large.")
        if len(buffer)<4+length:break
        frames.append(bytes(buffer[4:4+length]));del buffer[:4+length]
    return frames


def select_incoming_file(files,exists=None):
    exists=exists or (lambda path:path.exists())
    for raw_path in files:
        candidate=Path(raw_path).expanduser()
        if exists(candidate) and candidate.suffix.lower() in SUPPORTED_FILE_SUFFIXES:return candidate
    return None


def startup_decision(connect:Callable[[],bool],listen:Callable[[],bool],remove_stale:Callable[[],bool],retries=RETRY_COUNT):
    """Return ``secondary``, ``primary``, or ``failed`` using race-safe ordering."""
    if connect():return "secondary"
    if listen():return "primary"
    for _ in range(retries):
        if connect():return "secondary"
    remove_stale()
    if listen():return "primary"
    if connect():return "secondary"
    return "failed"


class SingleInstanceCoordinator(QObject):
    activationRequested=Signal(list)

    def __init__(self,server_name=None,parent=None):
        super().__init__(parent);self.server_name=server_name or instance_server_name();self.server=QLocalServer(self);self._buffers={}
        self.server.newConnection.connect(self._accept_connections)

    def _connect_and_send(self,payload):
        socket=QLocalSocket();socket.connectToServer(self.server_name)
        if not socket.waitForConnected(CONNECT_TIMEOUT_MS):socket.abort();return False
        data=encode_payload(payload);socket.write(data)
        if not socket.waitForBytesWritten(CONNECT_TIMEOUT_MS):socket.abort();return False
        socket.flush();socket.disconnectFromServer();socket.waitForDisconnected(CONNECT_TIMEOUT_MS);return True

    def become_primary_or_forward(self,payload):
        decision=startup_decision(lambda:self._connect_and_send(payload),lambda:self.server.listen(self.server_name),
                                  lambda:QLocalServer.removeServer(self.server_name))
        if decision=="primary":LOG.info("Single-instance server started")
        elif decision=="secondary":LOG.info("Existing Drillbit instance detected; forwarding request and exiting")
        else:LOG.error("Could not establish or contact the single-instance server")
        return decision

    def close(self):
        for socket in tuple(self._buffers):socket.abort()
        self._buffers.clear();self.server.close()

    def _accept_connections(self):
        while self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection();self._buffers[socket]=bytearray()
            socket.readyRead.connect(lambda current=socket:self._read_socket(current))
            socket.disconnected.connect(lambda current=socket:self._drop_socket(current))

    def _drop_socket(self,socket):self._buffers.pop(socket,None);socket.deleteLater()

    def _read_socket(self,socket):
        buffer=self._buffers.get(socket)
        if buffer is None:return
        buffer.extend(bytes(socket.readAll()))
        try:frames=extract_frames(buffer)
        except ValueError:
            LOG.warning("Rejected oversized single-instance request");socket.abort();self._buffers.pop(socket,None);return
        for body in frames:
            payload=decode_payload(body)
            if payload is None:LOG.warning("Ignored malformed single-instance request");continue
            files=payload["files"];LOG.info("Received activation request");LOG.info("Received file-open request: %s file(s)",len(files))
            self.activationRequested.emit(files)


class DrillbitApplication(QApplication):
    def notify(self,receiver,event):
        try:return super().notify(receiver,event)
        except Exception:
            from .logging_manager import log_unhandled_exception
            exc_type,exc_value,exc_traceback=sys.exc_info();log_unhandled_exception(exc_type,exc_value,exc_traceback);return False


def command_line_files(arguments):
    return [argument for argument in arguments[1:] if argument and not argument.startswith("-")]


def run(arguments=None,server_name=None):
    arguments=list(sys.argv if arguments is None else arguments)
    from .logging_manager import begin_session,configure_logging,end_session,install_exception_hooks
    configure_logging();install_exception_hooks()
    app=DrillbitApplication(arguments);app.setApplicationName("Drillbit");app.setOrganizationName("Drillbit")
    coordinator=SingleInstanceCoordinator(server_name);payload=activation_payload(command_line_files(arguments));decision=coordinator.become_primary_or_forward(payload)
    if decision=="secondary":return 0
    if decision!="primary":
        QMessageBox.critical(None,"Drillbit Startup","Drillbit could not start its single-instance service. Please try again.");return 1
    from .main_window import MainWindow,_crash_dialog
    previous_abnormal=begin_session();install_exception_hooks(_crash_dialog);window=MainWindow();coordinator.activationRequested.connect(window.handle_activation_request)
    app.aboutToQuit.connect(coordinator.close);app.aboutToQuit.connect(end_session);window.show()
    initial_files=payload["files"]
    if initial_files:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0,lambda:window.handle_activation_request(initial_files))
    if previous_abnormal:
        from PySide6.QtCore import QTimer
        def offer_logs():
            if QMessageBox.question(window,"Previous Session","Drillbit did not close normally last time. Open diagnostic logs?")==QMessageBox.StandardButton.Yes:window._open_log_folder()
        QTimer.singleShot(0,offer_logs)
    return app.exec()
