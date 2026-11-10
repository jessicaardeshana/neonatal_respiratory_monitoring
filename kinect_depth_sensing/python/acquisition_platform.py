"""Continuous Kinect acquisition panel. Run: python3 python/acquisition_platform.py"""
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
from acquisition_session import AcquisitionSession, PROJECT


def preview_ppm(pixels, name, width=350, height=240):
    """Downsample for display only; keep numerical recording untouched."""
    h, w = pixels.shape[:2]
    scale = min(width/w, height/h, 1.)
    yi = np.linspace(0, h-1, max(1, int(h*scale))).astype(int)
    xi = np.linspace(0, w-1, max(1, int(w*scale))).astype(int)
    small = pixels[yi[:, None], xi]
    if name != 'rgb':
        valid = np.isfinite(small)
        if name == 'depth':
            valid &= small > 0
        if name == 'depth':
            gray = 255 * (1 - (np.where(valid, small, 4500) - 500) / 4000)
        elif valid.any():
            lo, hi = np.percentile(small[valid], [2, 98])
            gray = 255 * (np.where(valid, small, lo) - lo) / max(float(hi-lo), 1.)
        else:
            gray = np.zeros(small.shape)
        gray = np.where(valid, np.clip(gray, 0, 255), 0).astype('u1')
        small = np.repeat(gray[..., None], 3, axis=2)
    rgb = np.ascontiguousarray(small, dtype='u1')
    return f'P6\n{rgb.shape[1]} {rgb.shape[0]}\n255\n'.encode() + rgb.tobytes()


class AcquisitionApp:
    def __init__(self, root, session=None):
        self.root = root
        self.session = session or AcquisitionSession()
        self.closing = False
        self.started_at = 0
        self.finished = False
        self.previous = None
        self.last_preview = {}
        self.photos = {}
        root.title('Kinect • Continuous acquisition')
        root.geometry('1180x790')
        root.minsize(900, 650)
        root.protocol('WM_DELETE_WINDOW', self.close)
        box = ttk.Frame(root, padding=18)
        box.pack(fill='both', expand=True)
        ttk.Label(box, text='Kinect data acquisition', font=('', 22, 'bold')).pack(anchor='w')
        ttk.Label(box, text='Continuous depth • infrared intensity • RGB | Records until you press Stop').pack(anchor='w', pady=(3, 15))
        row = ttk.Frame(box); row.pack(fill='x')
        self.folder = tk.StringVar(value=str(PROJECT / 'recordings'))
        ttk.Label(row, text='Save recordings in').pack(side='left')
        self.entry = ttk.Entry(row, textvariable=self.folder)
        self.entry.pack(side='left', fill='x', expand=True, padx=10)
        self.browse_button = ttk.Button(row, text='Choose folder', command=self.browse)
        self.browse_button.pack(side='left')
        controls = ttk.Frame(box); controls.pack(fill='x', pady=12)
        self.start_button = ttk.Button(controls, text='Start recording', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(controls, text='Stop recording', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        self.view_button = ttk.Button(controls, text='Review recording', command=self.review, state='disabled')
        self.view_button.pack(side='left')
        self.state = tk.StringVar(value='Ready — close Protonect before starting.')
        ttk.Label(controls, textvariable=self.state).pack(side='left', padx=15)
        self.details = tk.StringVar(value='Elapsed 00:00:00 | Saved 0.00 GiB')
        ttk.Label(box, textvariable=self.details, font=('', 12)).pack(anchor='w')
        self.path_label = tk.StringVar(value='Each Start creates a new session folder. Existing recordings are preserved.')
        ttk.Label(box, textvariable=self.path_label, wraplength=1100).pack(anchor='w', pady=(3, 10))
        previews = ttk.Frame(box); previews.pack(fill='x')
        self.panels, self.stats = {}, {}
        for i, (name, title) in enumerate([('depth', 'Depth · mm'), ('ir', 'IR · reflected intensity'), ('rgb', 'RGB · color')]):
            previews.columnconfigure(i, weight=1)
            cell = ttk.LabelFrame(previews, text=title, padding=8)
            cell.grid(row=0, column=i, sticky='nsew', padx=4)
            self.panels[name] = ttk.Label(cell, text='Waiting for frames', anchor='center')
            self.panels[name].pack(fill='both', expand=True)
            self.stats[name] = tk.StringVar(value='0 frames | — fps | 0 queue drops')
            ttk.Label(cell, textvariable=self.stats[name]).pack(pady=(8, 0))
        ttk.Label(box, text='Previews show the latest saved frame per stream; they are not synchronized or registered. IR is not temperature.').pack(anchor='w', pady=(10, 2))
        ttk.Label(box, text='Full-resolution storage can reach 18 GB/min. Capture stops automatically with less than 2 GiB free.').pack(anchor='w')
        ttk.Label(box, text='Acquisition log').pack(anchor='w', pady=(14, 3))
        self.log = tk.Text(box, height=9, wrap='word', state='disabled')
        self.log.pack(fill='both', expand=True)
        root.after(250, self.poll)

    def browse(self):
        folder = filedialog.askdirectory(initialdir=self.folder.get())
        if folder:
            self.folder.set(folder)

    def start(self):
        try:
            directory = self.session.start(self.folder.get())
        except Exception as e:
            messagebox.showerror('Could not start recording', str(e))
            return
        self.started_at = time.monotonic()
        self.finished = False
        self.previous = None
        self.last_preview.clear()
        self.photos.clear()
        for name in self.panels:
            self.panels[name].configure(image='', text='Waiting for frames')
            self.stats[name].set('0 frames | — fps | 0 queue drops')
        self.state.set('Connecting to Kinect…')
        self.path_label.set(str(directory))
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.view_button.configure(state='disabled')
        self.entry.configure(state='disabled')
        self.browse_button.configure(state='disabled')

    def stop(self):
        self.session.stop()
        self.stop_button.configure(state='disabled')
        self.state.set('Stopping — saving files and releasing camera…')

    def review(self):
        if self.session.directory and not self.session.running:
            subprocess.Popen([sys.executable, str(PROJECT / 'python' / 'view_recording.py'), str(self.session.directory)], cwd=PROJECT)

    def poll(self):
        try:
            if self.session.process is not None:
                status = self.session.status()
                running = self.session.running
                if status:
                    elapsed = status['elapsed_s']
                    size = sum(s['bytes'] for s in status['streams'].values()) / 2**30
                    free = status['free_bytes'] / 2**30
                    current = (elapsed, {n: s['frames'] for n, s in status['streams'].items()})
                    for name, info in status['streams'].items():
                        fps = '—'
                        if self.previous and elapsed > self.previous[0]:
                            fps = f"{(info['frames']-self.previous[1][name])/(elapsed-self.previous[0]):.1f}"
                        elif self.previous:
                            # Keep the last displayed rate until a new status arrives.
                            fps = self.stats[name].get().split(' | ')[1].split(' ')[0]
                        self.stats[name].set(f"{info['frames']:,} frames | {fps} fps | {info['queue_drops']:,} queue drops")
                        if info['frames'] and self.last_preview.get(name) != info['frames']:
                            pixels = self.session.latest_frame(name, status)
                            if pixels is not None:
                                photo = tk.PhotoImage(data=preview_ppm(pixels, name), format='PPM')
                                self.photos[name] = photo
                                self.panels[name].configure(image=photo, text='')
                                self.last_preview[name] = info['frames']
                    if self.previous is None or elapsed > self.previous[0]:
                        self.previous = current
                    if running and not self.session.stopping:
                        self.state.set('Recording continuously' if status['state'] == 'recording' else 'Finishing…')
                else:
                    elapsed = time.monotonic()-self.started_at
                    size = 0
                    try:
                        parent = self.session.directory.parent
                        free = shutil.disk_usage(parent).free / 2**30
                    except OSError:
                        free = 0
                seconds = int(elapsed)
                self.details.set(f'Elapsed {seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02} | Saved {size:.2f} GiB | Free {free:.1f} GiB')
                tail = self.session.log_tail()
                if self.log.get('1.0', 'end-1c') != tail:
                    self.log.configure(state='normal'); self.log.delete('1.0', 'end')
                    self.log.insert('1.0', tail); self.log.see('end'); self.log.configure(state='disabled')
                if not running and not self.finished:
                    self.finished = True
                    self.session.close_log()
                    code = self.session.process.returncode
                    reason = (status or {}).get('reason', 'See acquisition log')
                    self.state.set('Stopped — recording saved' if code == 0 else f'Stopped with an error — {reason}')
                    self.start_button.configure(state='normal')
                    self.stop_button.configure(state='disabled')
                    self.entry.configure(state='normal')
                    self.browse_button.configure(state='normal')
                    if status and all(s['frames'] > 0 for s in status['streams'].values()):
                        self.view_button.configure(state='normal')
                if self.closing and not running:
                    self.root.destroy()
                    return
        except (OSError, ValueError, KeyError, tk.TclError) as e:
            self.state.set(f'Preview/status issue: {e}. Recording may still be running.')
        self.root.after(250, self.poll)

    def close(self):
        if self.session.running:
            self.closing = True
            self.stop()
        else:
            self.session.close_log()
            self.root.destroy()


def main():
    root = tk.Tk()
    AcquisitionApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
