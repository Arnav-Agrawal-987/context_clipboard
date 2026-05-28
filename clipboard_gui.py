#!/usr/bin/env python3
# Context Clipboard GUI
# System tray app for search, history, and settings.

import ctypes
import os
# Important startup flags: set DPI awareness before tkinter creates any window.
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
except (AttributeError, OSError):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pystray
from PIL import Image, ImageDraw
import threading
from pathlib import Path
import win32con
import win32clipboard
import time

from clipboard_service import (
    DatabaseManager, DATA_DIR, DB_PATH, 
    AutoStartManager, APP_NAME, ClipboardMonitor
)

import logging
logger = logging.getLogger("ContextClipboard")

# Tooltip helper
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("Segoe UI", "9", "normal"), padx=8, pady=5)
        label.pack()

    def hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

# Search view
class SearchFrame(ttk.Frame):
    def __init__(self, parent, db: DatabaseManager, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        
        self.search_after_id = None
        self.tree = None
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        
        self.setup_ui()
    
    def setup_ui(self):
        search_frame = ttk.Frame(self)
        search_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(search_frame, text="🔍").pack(side='left')
        
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, font=('Segoe UI', 11))
        self.search_entry.pack(side='left', fill='x', expand=True, padx=5)
        self.search_entry.focus()
        
        info_btn = tk.Label(search_frame, text="ℹ️", cursor="hand2", font=('Segoe UI', 11))
        info_btn.pack(side='left', padx=(0, 5))
        Tooltip(info_btn, 
                "Search Syntax:\n"
                "• Plain text — searches clip content, app name, and window title\n"
                "• \"exact phrase\" — match words together in content\n"
                "• term1 AND term2 — both must appear\n"
                "• term1 OR term2 — either can appear\n"
                "• term NOT exclude — exclude a word\n"
                "• App names and window titles are always searched alongside content")
        
        ttk.Button(search_frame, text="Clear", command=self.clear_search).pack(side='right')
        
        self.tree = ttk.Treeview(self, columns=('time', 'app', 'preview', 'type'), show='headings', height=15)
        self.tree.heading('time', text='Time')
        self.tree.heading('app', text='Source')
        self.tree.heading('preview', text='Preview')
        self.tree.heading('type', text='Type')
        
        self.tree.column('time', width=100, anchor='w')
        self.tree.column('app', width=120, anchor='w')
        self.tree.column('preview', width=400, anchor='w')
        self.tree.column('type', width=60, anchor='center')
        
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side='left', fill='both', expand=True, padx=10, pady=5)
        scrollbar.pack(side='right', fill='y', pady=5)
        
        self.tree.bind('<Double-1>', self.on_double_click)
        self.tree.bind('<Return>', self.on_double_click)
        self.tree.bind('<Button-3>', self.show_context_menu)
        
        ttk.Label(self, textvariable=self.status_var, relief='sunken').pack(fill='x', padx=10, pady=2)
        
        self.search_var.trace_add('write', lambda *args: self.delayed_search())
        
        self.load_recent()
    
    def delayed_search(self):
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
        self.search_after_id = self.after(300, self.perform_search)
    
    def perform_search(self):
        query = self.search_var.get().strip()
        if not query:
            self.load_recent()
            return
        
        results = self.db.search(query)
        self.populate_tree(results)
        self.status_var.set(f"Found {len(results)} results for '{query}'")
    
    def load_recent(self):
        results = self.db.get_recent(hours=48, limit=100)
        self.populate_tree(results)
        self.status_var.set(f"Showing {len(results)} recent clips")
    
    def populate_tree(self, clips: list):
        if self.tree is None:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for clip in clips:
            time_str = clip.timestamp.strftime('%m-%d %H:%M')
            preview = clip.content.replace('\n', ' ')[:80]
            self.tree.insert('', 'end', values=(time_str, clip.source_app, preview, clip.content_type), tags=(str(clip.id),))
    
    def on_double_click(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        
        item = self.tree.item(selected[0])
        clip_id = int(item['tags'][0])
        self.show_clip_detail(clip_id)
    
    def show_clip_detail(self, clip_id: int):
        with self.db.get_conn() as conn:
            row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            if not row:
                return
            
            detail = tk.Toplevel(self)
            detail.title(f"Clip from {row['source_app']} - {row['timestamp']}")
            detail.geometry("600x500")
            detail.transient(self.winfo_toplevel())
            
            info = ttk.Frame(detail)
            info.pack(fill='x', padx=10, pady=5)
            
            ttk.Label(info, text=f"Source: {row['source_app']}", font=('Segoe UI', 10, 'bold')).pack(anchor='w')
            ttk.Label(info, text=f"Window: {row['source_window_title']}").pack(anchor='w')
            ttk.Label(info, text=f"Time: {row['timestamp']}").pack(anchor='w')
            
            text = scrolledtext.ScrolledText(detail, wrap=tk.WORD, font=('Consolas', 10))
            text.pack(fill='both', expand=True, padx=10, pady=5)
            text.insert('1.0', row['content'])
            text.config(state='disabled')
            
            btn_frame = ttk.Frame(detail)
            btn_frame.pack(fill='x', padx=10, pady=5)
            
            ttk.Button(btn_frame, text="Copy to Clipboard", 
                      command=lambda: self.copy_to_clipboard(row['content'])).pack(side='left', padx=2)
            ttk.Button(btn_frame, text="Open Source App", 
                      command=lambda: self.open_app(row['source_process_path'])).pack(side='left', padx=2)
            
            if row['screenshot_path'] and os.path.exists(row['screenshot_path']):
                ttk.Button(btn_frame, text="View Screenshot", 
                          command=lambda: os.startfile(row['screenshot_path'])).pack(side='left', padx=2)
    
    def copy_to_clipboard(self, text: str):
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        self.status_var.set("Copied to clipboard!")
    
    def open_app(self, path: str):
        if path and os.path.exists(path):
            os.startfile(path)
    
    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Copy", command=lambda: self.copy_selected())
            menu.add_command(label="Delete", command=lambda: self.delete_selected())
            menu.add_separator()
            menu.add_command(label="View Details", command=lambda: self.on_double_click(None))
            menu.post(event.x_root, event.y_root)
    
    def copy_selected(self):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            clip_id = int(item['tags'][0])
            with self.db.get_conn() as conn:
                row = conn.execute("SELECT content FROM clips WHERE id = ?", (clip_id,)).fetchone()
                if row:
                    self.copy_to_clipboard(row['content'])
    
    def delete_selected(self):
        selected = self.tree.selection()
        if selected:
            if messagebox.askyesno("Confirm", "Delete this clip?"):
                item = self.tree.item(selected[0])
                clip_id = int(item['tags'][0])
                with self.db.get_conn() as conn:
                    conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
                    conn.commit()
                self.perform_search()
    
    def clear_search(self):
        self.search_var.set('')
        self.load_recent()

# Settings view
class SettingsFrame(ttk.Frame):
    def __init__(self, parent, monitor=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.monitor = monitor
        self.setup_ui()
    
    def setup_ui(self):
        ttk.Label(self, text="Settings", font=('Segoe UI', 14, 'bold')).pack(pady=10)
        
        self.autostart_var = tk.BooleanVar(value=AutoStartManager.is_enabled())
        ttk.Checkbutton(self, text="Start with Windows", variable=self.autostart_var,
                       command=self.toggle_autostart).pack(anchor='w', padx=20, pady=5)
        
        self.screenshot_var = tk.BooleanVar(
            value=self.monitor.capture_screenshots if self.monitor else False
        )
        ttk.Checkbutton(self, text="Capture screenshots (uses more disk space)", 
                       variable=self.screenshot_var,
                       command=self.toggle_screenshots).pack(anchor='w', padx=20, pady=5)
        
        ttk.Separator(self, orient='horizontal').pack(fill='x', padx=10, pady=10)
        
        self.stats_frame = ttk.LabelFrame(self, text="Statistics", padding=10)
        self.stats_frame.pack(fill='x', padx=10, pady=5)
        
        self.stats_labels = {}
        for key in ['total_clips', 'today_clips']:
            frame = ttk.Frame(self.stats_frame)
            frame.pack(fill='x', pady=2)
            ttk.Label(frame, text=f"{key.replace('_', ' ').title()}:").pack(side='left')
            self.stats_labels[key] = ttk.Label(frame, text="0")
            self.stats_labels[key].pack(side='right')
        
        ttk.Button(self, text="Refresh Stats", command=self.refresh_stats).pack(pady=10)
        ttk.Button(self, text="Open Data Folder", command=lambda: os.startfile(DATA_DIR)).pack(pady=2)
        
        self.refresh_stats()
    
    def toggle_autostart(self):
        AutoStartManager.set_enabled(self.autostart_var.get())
    
    def toggle_screenshots(self):
        if self.monitor:
            self.monitor.capture_screenshots = self.screenshot_var.get()
            print(f"[Settings] Screenshots {'enabled' if self.monitor.capture_screenshots else 'disabled'}")
    
    def refresh_stats(self):
        db = DatabaseManager(DB_PATH)
        stats = db.get_stats()
        self.stats_labels['total_clips'].config(text=str(stats['total_clips']))
        self.stats_labels['today_clips'].config(text=str(stats['today_clips']))

# App shell
class ClipboardApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Context Clipboard")
        self.root.geometry("800x600")
        self.root.withdraw()
        
        self.db = DatabaseManager(DB_PATH)
        
        self.monitor = ClipboardMonitor(
            self.db,
            on_clip=self.on_new_clip,
            on_hotkey=self._on_hotkey,
            capture_screenshots=False
        )
        
        self.setup_ui()
        self.setup_tray()
        self.monitor.start()
    
    def _on_hotkey(self):
        logger.info("_on_hotkey called from monitor thread")
        self.root.after(0, self._show_search_safe)
    
    def _show_search_safe(self):
        logger.info("_show_search_safe executing")
        try:
            self.show_window()
            self.notebook.select(0)
            self.search_frame.search_entry.focus()
            self.search_frame.search_entry.select_range(0, 'end')
            logger.info("Search window should be visible now")
        except Exception as e:
            logger.error(f"Error showing search: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def show_window(self, *args):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        
        try:
            hwnd = int(self.root.winfo_id())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.FlashWindow(hwnd, True)
        except Exception as e:
            logger.error(f"SetForegroundWindow failed: {e}")
    
    def on_new_clip(self, entry):
        self.root.after(0, self._refresh_search)
    
    def _refresh_search(self):
        if not hasattr(self, 'search_frame'):
            return
        try:
            current = self.notebook.index(self.notebook.select())
            search_tab = self.notebook.index(self.search_frame)
            if current == search_tab:
                query = self.search_frame.search_var.get().strip()
                if query:
                    self.search_frame.perform_search()
                else:
                    self.search_frame.load_recent()
        except tk.TclError:
            pass
    
    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.search_frame = SearchFrame(self.notebook, self.db)
        self.notebook.add(self.search_frame, text="🔍 Search")
        
        self.settings_frame = SettingsFrame(self.notebook, monitor=self.monitor)
        self.notebook.add(self.settings_frame, text="⚙️ Settings")
        
        self.status_var = tk.StringVar(value="Running in background")
        ttk.Label(self.root, textvariable=self.status_var, relief='sunken').pack(fill='x')
        
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
    
    def setup_tray(self):
        image = Image.new('RGB', (64, 64), color='white')
        dc = ImageDraw.Draw(image)
        dc.rectangle([10, 10, 54, 54], fill='#0078D4', outline='#0078D4', width=2)
        dc.text((20, 22), "CC", fill='white')
        
        menu = pystray.Menu(
            pystray.MenuItem("Open", lambda icon, item: self.show_window()),
            pystray.MenuItem("Search", lambda icon, item: self.show_search()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: self.quit_app())
        )
        
        self.tray_icon = pystray.Icon(APP_NAME, image, "Context Clipboard", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        
    def show_search(self, *args):
        self.show_window()
        self.notebook.select(0)
        self.search_frame.search_entry.focus()
        self.search_frame.search_entry.select_range(0, 'end')
    
    def hide_window(self, *args):
        self.root.withdraw()
    
    def quit_app(self, *args):
        def delayed_exit():
            time.sleep(0.5)
            try:
                self.monitor.stop()
            except Exception as e:
                print(f"Monitor stop error: {e}")
            time.sleep(0.5)
            try:
                if self.tray_icon:
                    self.tray_icon.stop()
            except:
                pass
            try:
                self.root.quit()
                self.root.destroy()
            except:
                pass
            os._exit(0)
        
        threading.Thread(target=delayed_exit, daemon=True).start()
    
    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit_app()

def main():
    app = ClipboardApp()
    app.run()

if __name__ == "__main__":
    main()