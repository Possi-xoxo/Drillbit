import logging
from types import SimpleNamespace

from app import logging_manager as manager
from app.main_window import MainWindow
from PySide6.QtWidgets import QApplication


def flush_logs():
    for handler in logging.getLogger().handlers:handler.flush()


def test_log_directory_file_message_traceback_and_rotation(tmp_path):
    path=manager.configure_logging(tmp_path,max_bytes=1024,backup_count=3);log=logging.getLogger("test.logging")
    log.info("diagnostic info message")
    try:raise ValueError("controlled failure")
    except ValueError:log.exception("operation failed")
    flush_logs();text=path.read_text(encoding="utf-8")
    assert path==tmp_path/"drillbit.log" and "diagnostic info message" in text and "Traceback" in text and "controlled failure" in text
    handler=next(item for item in logging.getLogger().handlers if getattr(item,"_drillbit_handler",False))
    assert handler.maxBytes==1024 and handler.backupCount==3


def test_exception_helpers_include_thread_traceback_context_and_actions(tmp_path):
    path=manager.configure_logging(tmp_path);manager._actions.clear();manager.record_action("Loaded image");manager.set_diagnostic_context(pattern="400 x 253",max_colors=64)
    try:raise RuntimeError("worker exploded")
    except RuntimeError as exc:report=manager.log_worker_exception("ConversionWorker",exc)
    flush_logs();text=path.read_text(encoding="utf-8")
    assert "ConversionWorker" in report and "worker exploded" in report and "Loaded image" in report and "400 x 253" in report and "Traceback" in text


def test_thread_exception_hook_logs_thread_name(tmp_path):
    path=manager.configure_logging(tmp_path)
    try:raise LookupError("thread hook test")
    except LookupError as exc:manager._thread_exception_hook(SimpleNamespace(exc_type=type(exc),exc_value=exc,exc_traceback=exc.__traceback__,thread=SimpleNamespace(name="PaletteThread")))
    flush_logs();text=path.read_text(encoding="utf-8");assert "PaletteThread" in text and "thread hook test" in text


def test_crash_marker_detects_stale_session_and_normal_end(tmp_path):
    manager.configure_logging(tmp_path);marker=manager.get_marker_path();marker.write_text("stale",encoding="utf-8")
    assert manager.begin_session() is True and marker.exists()
    manager.end_session();assert not marker.exists()


def test_recent_actions_are_bounded(tmp_path):
    manager.configure_logging(tmp_path);manager._actions.clear()
    for index in range(manager.RECENT_ACTION_LIMIT+10):manager.record_action(f"action {index}")
    actions=manager.recent_actions();assert len(actions)==manager.RECENT_ACTION_LIMIT and "action 0" not in actions[0] and "action 10" in actions[0]


def test_paths_and_diagnostic_summary(tmp_path):
    manager.configure_logging(tmp_path);summary=manager.diagnostic_summary(Pattern="100 x 80",Colors=16)
    assert manager.get_log_directory()==tmp_path and manager.get_fault_log_path()==tmp_path/"drillbit_fault.log"
    assert "100 x 80" in summary and str(manager.get_log_path()) in summary


def test_diagnostics_menu_actions_exist():
    app=QApplication.instance() or QApplication([]);window=MainWindow()
    assert window.open_log_folder_action.text()=="Open Log Folder" and window.open_latest_log_action.text()=="Open Latest Log"
    assert window.copy_diagnostic_action.text()=="Copy Diagnostic Summary";window.close()
