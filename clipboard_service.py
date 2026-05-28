#!/usr/bin/env python3
# ContextClipboard — background clipboard capture service
# Captures clipboard entries with source context and optional screenshots.

import ctypes
import ctypes.wintypes as wintypes
import sqlite3
import threading
import time
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List
import win32api
import win32gui
import win32clipboard
import win32con
import win32process
import psutil
import sqlite3
import logging
import traceback
import hashlib
import winreg
from PIL import ImageGrab

def adapt_datetime_iso(val):
    return val.isoformat()

def convert_datetime(val):
    return datetime.fromisoformat(val.decode())

sqlite3.register_adapter(datetime, adapt_datetime_iso)
sqlite3.register_converter("datetime", convert_datetime)

def _set_dpi_aware():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass

_set_dpi_aware()

# Application configuration
APP_NAME = "ContextClipboard"
# Base data directory (per-user local app data)
DATA_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / APP_NAME
# Database and screenshot locations
DB_PATH = DATA_DIR / "clipboard.db"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
# Limits and retention policy
MAX_TEXT_LENGTH = 100000
RETENTION_DAYS = 30

DATA_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Windows message and modifier constants used for hotkeys and clipboard events
WM_HOTKEY = 0x0312
MOD_WIN = 0x0008
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_V = 0x56
WM_CLIPBOARDUPDATE = 0x031D
WM_QUIT = 0x0012
GW_OWNER = 4

# Log file for runtime info and errors
LOG_PATH = DATA_DIR / "context_clipboard.log"
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(APP_NAME)

@dataclass
class ClipEntry:
    id: Optional[int]
    content: str
    content_type: str
    source_app: str
    source_window_title: str
    source_process_path: str
    timestamp: datetime
    screenshot_path: Optional[str]
    hash: str
    
    def to_dict(self):
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d

class DatabaseManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_db()
    
    def get_conn(self):
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        with self.get_conn() as conn:
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    content_type TEXT DEFAULT 'text',
                    source_app TEXT,
                    source_window_title TEXT,
                    source_process_path TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    screenshot_path TEXT,
                    hash TEXT UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS clips_fts USING fts5(
                    content, 
                    source_app, 
                    source_window_title,
                    content='clips',
                    content_rowid='id'
                )
            """)
            
            
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS clips_ai AFTER INSERT ON clips BEGIN
                    INSERT INTO clips_fts(rowid, content, source_app, source_window_title)
                    VALUES (new.id, new.content, new.source_app, new.source_window_title);
                END
            """)
            
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS clips_ad AFTER DELETE ON clips BEGIN
                    INSERT INTO clips_fts(clips_fts, rowid, content, source_app, source_window_title)
                    VALUES ('delete', old.id, old.content, old.source_app, old.source_window_title);
                END
            """)
            
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON clips(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON clips(hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source_app ON clips(source_app)")
            
            conn.commit()
    
    def insert_clip(self, entry: ClipEntry) -> bool:
        try:
            with self.get_conn() as conn:
                cursor = conn.execute("""
                    INSERT INTO clips (content, content_type, source_app, source_window_title, 
                                     source_process_path, timestamp, screenshot_path, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.content[:MAX_TEXT_LENGTH],
                    entry.content_type,
                    entry.source_app,
                    entry.source_window_title,
                    entry.source_process_path,
                    entry.timestamp,
                    entry.screenshot_path,
                    entry.hash
                ))
                entry.id = cursor.lastrowid
                return True
        except sqlite3.IntegrityError:
            # Duplicate hash
            return False
    def _escape_fts5(self, query: str) -> str:
        return '"' + query.replace('"', '""') + '"'
    
    def search(self, query: str, limit: int = 50) -> List[ClipEntry]:
        with self.get_conn() as conn:
            stripped = query.strip()
            
            # Check if user provided their own FTS5 syntax
            has_fts_syntax = any(op in stripped.upper() for op in ['AND', 'OR', 'NOT', '"', '*'])
            
            if has_fts_syntax:
                fts_query = stripped.replace('"', '""')
                if not fts_query.startswith('"'):
                    fts_query = f'"{fts_query}"'
            else:
                # Prefix matching: "dele" becomes "dele*" so it matches "delete", "deleted", etc.
                words = stripped.split()
                if words:
                    fts_query = ' '.join(f'"{w.replace('"', '""')}*"' for w in words)
                else:
                    fts_query = '""'
            
            try:
                rows = conn.execute("""
                    SELECT * FROM clips
                    WHERE id IN (
                        SELECT rowid FROM clips_fts 
                        WHERE clips_fts MATCH ?
                    )
                    OR content LIKE ?
                    OR source_app LIKE ? 
                    OR source_window_title LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (fts_query, f'%{query}%', f'%{query}%', f'%{query}%', limit)).fetchall()
            except sqlite3.OperationalError:
                rows = conn.execute("""
                    SELECT * FROM clips
                    WHERE content LIKE ? 
                    OR source_app LIKE ? 
                    OR source_window_title LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (f'%{query}%', f'%{query}%', f'%{query}%', limit)).fetchall()
            
            return [self._row_to_entry(row) for row in rows]
    
    def get_recent(self, hours: int = 24, limit: int = 100) -> List[ClipEntry]:
        with self.get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM clips 
                WHERE timestamp > datetime('now', '-{} hours')
                ORDER BY timestamp DESC
                LIMIT ?
            """.format(hours), (limit,)).fetchall()
            return [self._row_to_entry(row) for row in rows]
    
    def get_stats(self) -> dict:
        with self.get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
            today = conn.execute("""
                SELECT COUNT(*) FROM clips 
                WHERE date(timestamp) = date('now')
            """).fetchone()[0]
            apps = conn.execute("""
                SELECT source_app, COUNT(*) as count 
                FROM clips 
                WHERE source_app IS NOT NULL 
                GROUP BY source_app 
                ORDER BY count DESC 
                LIMIT 5
            """).fetchall()
            return {
                'total_clips': total,
                'today_clips': today,
                'top_apps': [dict(row) for row in apps]
            }
    
    def cleanup_old(self, days: int = RETENTION_DAYS):
        with self.get_conn() as conn:
            conn.execute("""
                DELETE FROM clips 
                WHERE timestamp < datetime('now', '-{} days')
            """.format(days))
            conn.commit()
    
    def _row_to_entry(self, row) -> ClipEntry:
        return ClipEntry(
            id=row['id'],
            content=row['content'],
            content_type=row['content_type'],
            source_app=row['source_app'],
            source_window_title=row['source_window_title'],
            source_process_path=row['source_process_path'],
            timestamp=row['timestamp'],
            screenshot_path=row['screenshot_path'],
            hash=row['hash']
        )

# Window Context Capture
class WindowContext:
    @staticmethod
    def get_active_window_info() -> dict:
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return {'app': 'Unknown', 'title': 'Unknown', 'path': ''}
            
            # Get window title
            title = win32gui.GetWindowText(hwnd)
            
            # Get process info
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                process = psutil.Process(pid)
                app_name = process.name().replace('.exe', '').title()
                exe_path = process.exe()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                app_name = 'Unknown'
                exe_path = ''
            
            return {
                'app': app_name,
                'title': title,
                'path': exe_path,
                'pid': pid
            }
        except Exception:
            return {'app': 'Unknown', 'title': 'Unknown', 'path': ''}

# Screenshot Capture
class ScreenshotCapture:
    @staticmethod
    def capture_fullscreen() -> Optional[str]:
        try:            
            img = ImageGrab.grab()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screen_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename
            
            img.save(filepath, "PNG")
            logger.info(f"[Screenshot] Saved {img.size[0]}x{img.size[1]}: {filepath.name}")
            return str(filepath)
        except Exception as e:
            logger.info(f"Screenshot error: {e}")
            traceback.logger.info_exc()
            return None

# Clipboard Monitor
class ClipboardMonitor:
    def __init__(self, db: DatabaseManager, on_clip: Callable = None, 
                 on_hotkey: Callable = None, capture_screenshots: bool = False):
        self.db = db
        self.on_clip = on_clip
        self.on_hotkey = on_hotkey
        self.capture_screenshots = capture_screenshots
        self._hwnd = None
        self._running = False
        self._last_hash = None
        self._thread_id = None
        self._hotkey_id = None
        
    def _create_window(self) -> int:
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc
        wc.lpszClassName = "ContextClipboardListener"
        wc.hInstance = win32api.GetModuleHandle(None)
        
        class_atom = win32gui.RegisterClass(wc)
        hwnd = win32gui.CreateWindow(
            class_atom, 
            "ContextClipboardListener",
            0, 0, 0, 0, 0,
            0, 0, 
            wc.hInstance, 
            None
        )
        
        if self.on_hotkey:
            # Try Win+Shift+V
            HOTKEY_ID = 0xBABE
            result = ctypes.windll.user32.RegisterHotKey(hwnd, HOTKEY_ID, MOD_WIN | MOD_SHIFT, VK_V)
            if result:
                self._hotkey_id = HOTKEY_ID
                logger.info("Hotkey registered: Win+Shift+V")
            else:
                err = ctypes.windll.kernel32.GetLastError()
                logger.warning(f"Win+Shift+V failed (error {err}), trying fallback...")
                
                # Fallback: Ctrl+Shift+V
                HOTKEY_ID2 = 0xBABF
                result2 = ctypes.windll.user32.RegisterHotKey(hwnd, HOTKEY_ID2, MOD_CONTROL | MOD_SHIFT, VK_V)
                if result2:
                    self._hotkey_id = HOTKEY_ID2
                    logger.info("Hotkey registered: Ctrl+Shift+V")
                else:
                    err2 = ctypes.windll.kernel32.GetLastError()
                    logger.error(f"Ctrl+Shift+V also failed (error {err2})")
        
        return hwnd
    
    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int):
        if msg == WM_CLIPBOARDUPDATE:
            self._handle_clipboard_change()
        elif msg == WM_HOTKEY:
            logger.info(f"WM_HOTKEY received: id={wparam}, expected={self._hotkey_id}")
            if self._hotkey_id and wparam == self._hotkey_id and self.on_hotkey:
                try:
                    logger.info("Calling on_hotkey callback...")
                    self.on_hotkey()
                except Exception as e:
                    logger.error(f"Hotkey callback error: {e}")
                    logger.error(traceback.format_exc())
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
    
    def _handle_clipboard_change(self):
        try:
            win32clipboard.OpenClipboard()
            
            content = None
            content_type = 'text'
            
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                content = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            elif win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
                content = win32clipboard.GetClipboardData(win32con.CF_TEXT)
                if isinstance(content, bytes):
                    content = content.decode('utf-8', errors='ignore')
            elif win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP):
                files = win32clipboard.GetClipboardData(win32con.CF_HDROP)
                content = '\n'.join(files)
                content_type = 'file'
            
            win32clipboard.CloseClipboard()
            
            if not content or not isinstance(content, str):
                return
            if len(content.strip()) < 2:
                return
            
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            if content_hash == self._last_hash:
                return
            self._last_hash = content_hash
            
            context = WindowContext.get_active_window_info()
            
            screenshot_path = None
            if self.capture_screenshots:
                screenshot_path = ScreenshotCapture.capture_fullscreen()
            
            entry = ClipEntry(
                id=None,
                content=content,
                content_type=content_type,
                source_app=context['app'],
                source_window_title=context['title'],
                source_process_path=context['path'],
                timestamp=datetime.now(),
                screenshot_path=screenshot_path,
                hash=content_hash
            )
            
            if self.db.insert_clip(entry):
                logger.info(f"Captured from {entry.source_app}: {entry.content[:60]}...")
                if self.on_clip:
                    self.on_clip(entry)
                    
        except Exception as e:
            logger.error(f"Clipboard error: {e}")
            try:
                win32clipboard.CloseClipboard()
            except:
                pass
    
    def start(self):
        self._running = True
        def run():
            self._hwnd = self._create_window()
            self._thread_id = win32api.GetCurrentThreadId()
            ctypes.windll.user32.AddClipboardFormatListener(self._hwnd)
            logger.info("Clipboard monitoring started")
            
            # Explicit PeekMessage loop instead of PumpWaitingMessages
            PM_REMOVE = 0x0001
            msg = ctypes.wintypes.MSG()
            
            while self._running:
                while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                    ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.01)
            
            # Cleanup
            if self._hotkey_id:
                ctypes.windll.user32.UnregisterHotKey(self._hwnd, self._hotkey_id)
            ctypes.windll.user32.RemoveClipboardFormatListener(self._hwnd)
            win32gui.DestroyWindow(self._hwnd)
            self._hwnd = None
            logger.info("Clipboard monitoring stopped")
        
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._running = False
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if hasattr(self, '_thread') and self._thread.is_alive():
            self._thread.join(timeout=1.0)

# Auto-start Manager
class AutoStartManager:
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    @classmethod
    def is_enabled(cls) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH)
            winreg.QueryValueEx(key, "Context Clipboard")
            winreg.CloseKey(key)
            return True
        except:
            return False
    
    @classmethod
    def set_enabled(cls, enabled: bool):
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_SET_VALUE)
        
        if enabled:
            exe_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
            winreg.SetValueEx(key, "Context Clipboard", 0, winreg.REG_SZ, f'"{exe_path}"')
        else:
            try:
                winreg.DeleteValue(key, "Context Clipboard")
            except:
                pass
        
        winreg.CloseKey(key)

# Main Service
class ClipboardService:
    def __init__(self):
        self.db = DatabaseManager(DB_PATH)
        self.monitor = ClipboardMonitor(self.db, capture_screenshots=False)
        self.cleanup_interval = 3600
    
    def start(self):
        self.monitor.start()
        
        # Periodic cleanup thread
        def cleanup_loop():
            while True:
                time.sleep(self.cleanup_interval)
                self.db.cleanup_old()
                logger.info("Cleaned up old clips")
        
        threading.Thread(target=cleanup_loop, daemon=True).start()
        
        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        self.monitor.stop()
        logger.info("Service stopped")

if __name__ == "__main__":
    service = ClipboardService()
    service.start()