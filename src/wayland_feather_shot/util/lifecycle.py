"""Process lifecycle helpers: application holds and the capture lock.

Import-light: nothing here imports gi at module level, so the GTK-free
tests (and cli, before it loads GTK) can use it.
"""

import errno
import os
from typing import Optional


class _NoLock:
    """Stands in for the lock when its file cannot be created: capturing
    without the guard beats not capturing at all."""

    def close(self):
        pass


def acquire_capture_lock(directory: Optional[str] = None):
    """Hold the per-user capture lock, or return None when a capture is open.

    A capture is fullscreen and interactive; a second Ctrl+PrtSc while the
    overlay is up would only stack another one on top of it. The lock is an
    flock on a file in the runtime directory, so it dies with the process and
    a crash cannot leave it behind.
    """
    import fcntl
    if directory is None:
        from gi.repository import GLib
        directory = GLib.get_user_runtime_dir() or GLib.get_user_cache_dir()
    try:
        os.makedirs(directory, exist_ok=True)
        handle = open(os.path.join(directory,
                                   "wayland-feather-shot.capture.lock"), "w")
    except OSError:
        return _NoLock()
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        handle.close()
        # Only "someone holds it" means a capture is open; a filesystem
        # without locks (NFS home, no runtime dir) must not block capturing.
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            return None
        return _NoLock()
    return handle


def release_on_window_removed(app, window):
    """Release a caller-owned hold once *window* leaves *app*.

    GTK holds the application for registered windows, but a separate manual
    hold needs its own release.  Widget disposal can happen after the window
    has closed, so the widget's ``destroy`` signal is too late for this job.
    """

    def on_removed(_app, removed):
        if removed is not window:
            return
        app.disconnect(handler_id)
        app.release()

    handler_id = app.connect("window-removed", on_removed)
