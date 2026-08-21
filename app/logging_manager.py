"""Local rotating logs, crash hooks, session markers, and recent-action diagnostics."""
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import sys
import tempfile
import threading
import traceback

from . import __version__

LOG_NAME="drillbit.log";FAULT_NAME="drillbit_fault.log";MARKER_NAME="session.running"
MAX_LOG_BYTES=3*1024*1024;BACKUP_COUNT=7;RECENT_ACTION_LIMIT=75
_actions=deque(maxlen=RECENT_ACTION_LIMIT);_log_dir=None;_fault_stream=None;_dialog_callback=None;_session_started=None;_current_context={}


def _preferred_log_dir():
    root=os.environ.get("LOCALAPPDATA")
    return Path(root)/"Drillbit"/"logs" if root else Path.home()/"AppData"/"Local"/"Drillbit"/"logs"


def _safe_directory(preferred=None):
    for candidate in (Path(preferred) if preferred else _preferred_log_dir(),Path(tempfile.gettempdir())/"Drillbit"/"logs"):
        try:candidate.mkdir(parents=True,exist_ok=True);return candidate
        except OSError:continue
    return Path(tempfile.gettempdir())


def get_log_directory():
    global _log_dir
    if _log_dir is None:_log_dir=_safe_directory()
    return _log_dir


def get_log_path():return get_log_directory()/LOG_NAME
def get_fault_log_path():return get_log_directory()/FAULT_NAME
def get_marker_path():return get_log_directory()/MARKER_NAME
def recent_actions():return list(_actions)


def record_action(message):
    entry=f"{datetime.now().astimezone().isoformat(timespec='seconds')} | {message}";_actions.append(entry);logging.getLogger("app.actions").info(message)


def set_diagnostic_context(**values):
    _current_context.update({key:value for key,value in values.items() if value is not None})


def configure_logging(log_directory=None,level=logging.INFO,max_bytes=MAX_LOG_BYTES,backup_count=BACKUP_COUNT):
    global _log_dir
    _log_dir=_safe_directory(log_directory);root=logging.getLogger();root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler,"_drillbit_handler",False):root.removeHandler(handler);handler.close()
    formatter=logging.Formatter("%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | %(message)s","%Y-%m-%d %H:%M:%S")
    try:
        handler=RotatingFileHandler(get_log_path(),maxBytes=max_bytes,backupCount=backup_count,encoding="utf-8");handler.setFormatter(formatter);handler._drillbit_handler=True;root.addHandler(handler)
    except OSError:
        handler=logging.StreamHandler(sys.stderr);handler.setFormatter(formatter);handler._drillbit_handler=True;root.addHandler(handler)
    return get_log_path()


def _enable_faulthandler():
    global _fault_stream
    try:
        fault_path=get_fault_log_path()
        if fault_path.exists() and fault_path.stat().st_size>MAX_LOG_BYTES:
            backup=fault_path.with_suffix(".log.1");backup.unlink(missing_ok=True);fault_path.replace(backup)
        _fault_stream=open(fault_path,"a",encoding="utf-8");faulthandler.enable(file=_fault_stream,all_threads=True)
    except (OSError,RuntimeError):logging.getLogger(__name__).exception("Could not enable faulthandler")


def begin_session():
    global _session_started
    log=logging.getLogger(__name__);marker=get_marker_path();previous_abnormal=marker.exists();_session_started=datetime.now(timezone.utc).isoformat()
    if previous_abnormal:log.warning("Previous session appears to have ended unexpectedly.")
    try:marker.write_text(_session_started,encoding="utf-8")
    except OSError:log.exception("Could not write session marker")
    log.info("===== Drillbit session started =====")
    log.info("Version=%s Python=%s OS=%s packaged=%s executable=%s CPUs=%s",__version__,platform.python_version(),platform.platform(),bool(getattr(sys,"frozen",False)),sys.executable,os.cpu_count())
    try:
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion
        log.info("PySide6=%s Qt=%s",pyside_version,qVersion())
    except Exception:log.exception("Could not read Qt version information")
    _enable_faulthandler();record_action("Application session started")
    return previous_abnormal


def end_session():
    logging.getLogger(__name__).info("===== Drillbit session ended normally =====")
    try:get_marker_path().unlink(missing_ok=True)
    except OSError:logging.getLogger(__name__).exception("Could not remove session marker")
    for handler in logging.getLogger().handlers:
        try:handler.flush()
        except Exception:pass


def format_crash_report(exc_type,exc_value,exc_traceback,thread_name=None):
    lines=["===== UNHANDLED EXCEPTION =====",f"Thread: {thread_name or threading.current_thread().name}"]
    if _current_context:lines.extend(f"{key}: {value}" for key,value in _current_context.items())
    lines.append("Recent actions:");lines.extend(f"- {action}" for action in recent_actions());lines.append("Traceback:")
    lines.extend(traceback.format_exception(exc_type,exc_value,exc_traceback));return "\n".join(lines)


def log_unhandled_exception(exc_type,exc_value,exc_traceback,thread_name=None,show_dialog=True):
    report=format_crash_report(exc_type,exc_value,exc_traceback,thread_name);logging.getLogger("app.crash").critical(report)
    if show_dialog and _dialog_callback:
        try:_dialog_callback(report)
        except Exception:logging.getLogger("app.crash").exception("Crash dialog failed")
    return report


def _sys_exception_hook(exc_type,exc_value,exc_traceback):
    if issubclass(exc_type,KeyboardInterrupt):return sys.__excepthook__(exc_type,exc_value,exc_traceback)
    log_unhandled_exception(exc_type,exc_value,exc_traceback)


def _thread_exception_hook(args):log_unhandled_exception(args.exc_type,args.exc_value,args.exc_traceback,args.thread.name,False)


def install_exception_hooks(dialog_callback=None):
    global _dialog_callback
    _dialog_callback=dialog_callback;sys.excepthook=_sys_exception_hook
    if hasattr(threading,"excepthook"):threading.excepthook=_thread_exception_hook


def log_worker_exception(worker_name,exc):return log_unhandled_exception(type(exc),exc,exc.__traceback__,worker_name,False)


@contextmanager
def log_timing(operation,logger=None,level=logging.INFO,**context):
    log=logger or logging.getLogger(__name__);started=datetime.now().timestamp();record_action(f"Started {operation}")
    if context:log.log(level,"Starting %s | %s",operation," ".join(f"{key}={value}" for key,value in context.items()))
    else:log.log(level,"Starting %s",operation)
    try:yield
    except Exception:
        log.exception("%s failed after %.3f seconds",operation,datetime.now().timestamp()-started);raise
    else:log.log(level,"%s completed in %.3f seconds",operation,datetime.now().timestamp()-started);record_action(f"Completed {operation}")


def diagnostic_summary(**current):
    values={"Drillbit version":__version__,"Operating system":platform.platform(),"Mode":"Packaged" if getattr(sys,"frozen",False) else "Source",
            "Current log":str(get_log_path()),"Session started":_session_started or "Not started",**current}
    return "\n".join(f"{key}: {value}" for key,value in values.items())
