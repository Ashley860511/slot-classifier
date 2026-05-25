import contextlib
import importlib
import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from .config import OUTPUT_DIR
except ImportError:
    APP_DIR = Path(__file__).resolve().parent
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from config import OUTPUT_DIR


def _runtime_app_dir():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "app"
    return Path(__file__).resolve().parent


def _load_run_classifier():
    app_dir = _runtime_app_dir()
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    return importlib.import_module("main").run_classifier


VIDEO_FILE_TYPES = [
    ("Video files", "*.mp4 *.mov *.avi *.mkv *.webm"),
    ("MP4", "*.mp4"),
    ("MOV", "*.mov"),
    ("All files", "*.*"),
]

MAX_LOG_CHARS = 120_000
MAX_QUEUE_EVENTS_PER_TICK = 120


def default_output_dir():
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent / "project" / "output")
    return str(OUTPUT_DIR)


class QueueWriter:
    def __init__(self, event_queue):
        self.event_queue = event_queue
        self.buffer = []
        self.buffer_size = 0

    def write(self, text):
        if not text:
            return
        self.buffer.append(text)
        self.buffer_size += len(text)
        if "\n" in text or self.buffer_size >= 2000:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        self.event_queue.put(("log", "".join(self.buffer)))
        self.buffer = []
        self.buffer_size = 0


class SlotClassifierApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Slot Classifier")
        self.geometry("900x620")
        self.minsize(760, 520)

        self.video_paths = []
        self.output_dirs = []
        self.worker = None
        self.event_queue = queue.Queue()

        self.output_dir_var = tk.StringVar(value=default_output_dir())
        self.status_var = tk.StringVar(value="請先選擇要分類的影片")
        self.percent_var = tk.StringVar(value="0%")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.skip_symbols_var = tk.BooleanVar(value=False)
        self.symbol_debug_var = tk.BooleanVar(value=False)
        self.pending_log = []

        self._build_ui()
        self.after(120, self._poll_events)

    def _build_ui(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(outer, text="Slot Classifier", font=("Segoe UI", 18, "bold"))
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(
            outer,
            text="選擇影片後開始分類，完成後可直接開啟輸出資料夾。",
            foreground="#555555",
        )
        subtitle.pack(anchor=tk.W, pady=(2, 14))

        file_row = ttk.Frame(outer)
        file_row.pack(fill=tk.X)
        ttk.Button(file_row, text="選擇影片", command=self.choose_videos).pack(side=tk.LEFT)
        ttk.Button(file_row, text="清除清單", command=self.clear_videos).pack(side=tk.LEFT, padx=(8, 0))

        self.video_list = tk.Listbox(outer, height=7, activestyle="none")
        self.video_list.pack(fill=tk.X, pady=(8, 14))

        output_row = ttk.Frame(outer)
        output_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(output_row, text="輸出資料夾").pack(side=tk.LEFT)
        output_entry = ttk.Entry(output_row, textvariable=self.output_dir_var)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(output_row, text="瀏覽", command=self.choose_output_dir).pack(side=tk.LEFT)

        option_row = ttk.Frame(outer)
        option_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Checkbutton(
            option_row,
            text="只分類截圖，不產生 symbol_table",
            variable=self.skip_symbols_var,
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            option_row,
            text="輸出 symbol debug 圖",
            variable=self.symbol_debug_var,
        ).pack(side=tk.LEFT, padx=(18, 0))

        action_row = ttk.Frame(outer)
        action_row.pack(fill=tk.X, pady=(0, 10))
        self.start_button = ttk.Button(action_row, text="開始分類", command=self.start_classification)
        self.start_button.pack(side=tk.LEFT)
        self.open_output_button = ttk.Button(
            action_row,
            text="開啟輸出資料夾",
            command=self.open_latest_output,
            state=tk.DISABLED,
        )
        self.open_output_button.pack(side=tk.LEFT, padx=(8, 0))

        progress_row = ttk.Frame(outer)
        progress_row.pack(fill=tk.X, pady=(0, 8))
        self.progress = ttk.Progressbar(
            progress_row,
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
        )
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(progress_row, textvariable=self.percent_var, width=6, anchor=tk.E).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(outer, textvariable=self.status_var).pack(anchor=tk.W, pady=(0, 8))

        log_frame = ttk.LabelFrame(outer, text="執行紀錄")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def choose_videos(self):
        paths = filedialog.askopenfilenames(
            title="選擇要分類的影片",
            filetypes=VIDEO_FILE_TYPES,
        )
        if not paths:
            return
        existing = set(self.video_paths)
        for path in paths:
            if path not in existing:
                self.video_paths.append(path)
                self.video_list.insert(tk.END, path)
        self.status_var.set(f"已選擇 {len(self.video_paths)} 支影片")

    def clear_videos(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("執行中", "分類執行中，暫時不能清除清單。")
            return
        self.video_paths = []
        self.video_list.delete(0, tk.END)
        self.status_var.set("請先選擇要分類的影片")

    def choose_output_dir(self):
        path = filedialog.askdirectory(title="選擇輸出資料夾")
        if path:
            self.output_dir_var.set(path)

    def start_classification(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("執行中", "分類器正在執行。")
            return
        if not self.video_paths:
            messagebox.showwarning("尚未選擇影片", "請先選擇至少一支影片。")
            return

        output_root = self.output_dir_var.get().strip()
        if not output_root:
            messagebox.showwarning("尚未選擇輸出資料夾", "請選擇輸出資料夾。")
            return

        self.output_dirs = []
        self._clear_log()
        self.start_button.configure(state=tk.DISABLED)
        self.open_output_button.configure(state=tk.DISABLED)
        self.progress_var.set(0.0)
        self.percent_var.set("0%")
        self.status_var.set("準備開始分類...")

        video_paths = list(self.video_paths)
        skip_symbols = self.skip_symbols_var.get()
        symbol_debug = self.symbol_debug_var.get()

        self.worker = threading.Thread(
            target=self._run_worker,
            args=(video_paths, output_root, skip_symbols, symbol_debug),
            daemon=True,
        )
        self.worker.start()

    def _run_worker(self, video_paths, output_root, skip_symbols, symbol_debug):
        def progress_callback(event):
            self.event_queue.put(("progress", event))

        writer = QueueWriter(self.event_queue)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                run_classifier = _load_run_classifier()
                outputs = run_classifier(
                    video_paths=video_paths,
                    output_root=output_root,
                    skip_symbols=skip_symbols,
                    symbol_debug=symbol_debug,
                    progress_callback=progress_callback,
                )
            writer.flush()
            self.event_queue.put(("done", outputs))
        except Exception:
            writer.flush()
            self.event_queue.put(("error", traceback.format_exc()))

    def _poll_events(self):
        handled = 0
        try:
            while handled < MAX_QUEUE_EVENTS_PER_TICK:
                kind, payload = self.event_queue.get_nowait()
                if kind == "log":
                    self.pending_log.append(payload)
                elif kind == "progress":
                    self._handle_progress(payload)
                elif kind == "done":
                    self._handle_done(payload)
                elif kind == "error":
                    self._handle_error(payload)
                handled += 1
        except queue.Empty:
            pass
        self._flush_pending_log()
        self.after(120, self._poll_events)

    def _handle_progress(self, event):
        message = event.get("message") or ""
        current = event.get("current") or 0
        total = event.get("total") or 0
        if current and total:
            self.status_var.set(f"{message} ({current}/{total})")
        else:
            self.status_var.set(message)
        if event.get("percent") is not None:
            percent = max(0.0, min(100.0, float(event.get("percent") or 0.0)))
            self.progress_var.set(percent)
            self.percent_var.set(f"{percent:.0f}%")
        output_dir = event.get("output_dir")
        if output_dir and output_dir not in self.output_dirs:
            self.output_dirs.append(output_dir)

    def _handle_done(self, outputs):
        self.progress_var.set(100.0)
        self.percent_var.set("100%")
        self.start_button.configure(state=tk.NORMAL)
        self.output_dirs = list(outputs or self.output_dirs)
        if self.output_dirs:
            self.open_output_button.configure(state=tk.NORMAL)
            self.status_var.set(f"完成，輸出 {len(self.output_dirs)} 個資料夾")
        else:
            self.status_var.set("完成，但沒有產生輸出資料夾")
        messagebox.showinfo("完成", self.status_var.get())

    def _handle_error(self, text):
        self.start_button.configure(state=tk.NORMAL)
        self._append_log("\n" + text)
        self.status_var.set("執行失敗，請查看執行紀錄")
        messagebox.showerror("執行失敗", "分類時發生錯誤，請查看執行紀錄。")

    def open_latest_output(self):
        target = self.output_dirs[-1] if self.output_dirs else self.output_dir_var.get().strip()
        if not target:
            return
        if not os.path.exists(target):
            messagebox.showwarning("找不到資料夾", target)
            return
        os.startfile(target)

    def _append_log(self, text):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text)
        extra = int(self.log_text.count("1.0", tk.END, "chars")[0]) - MAX_LOG_CHARS
        if extra > 0:
            self.log_text.delete("1.0", f"1.0+{extra}c")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _flush_pending_log(self):
        if not self.pending_log:
            return
        text = "".join(self.pending_log)
        self.pending_log = []
        self._append_log(text)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)


def main():
    app = SlotClassifierApp()
    app.mainloop()


if __name__ == "__main__":
    main()
