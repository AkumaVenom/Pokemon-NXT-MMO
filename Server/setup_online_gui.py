"""Native online-hosting setup. Worker threads never access Tk objects."""
from __future__ import annotations

import os
from pathlib import Path
import queue
import threading

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None

from setup_online import SetupError, SetupOptions, configure


class GuiUnavailable(RuntimeError):
    pass


class SetupWindow:
    def __init__(self, root: tk.Tk, config_path: Path):
        self.root = root
        self.path = config_path.resolve()
        self.busy = False
        self.success = False
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.controls: list = []
        self.import_controls: list = []
        self.wrap_labels: list = []
        self.host = tk.StringVar(root, '')
        self.mode = tk.StringVar(root, 'generate')
        self.certificate = tk.StringVar(root, '')
        self.private_key = tk.StringVar(root, '')
        self.status = tk.StringVar(root, 'Ready. Enter the exact hostname or IP your players will use.')
        self.result_text = ''

        root.title('Pokemon NXT MMO - Online Hosting Setup')
        width = max(1, min(880, root.winfo_screenwidth() - 80))
        height = max(1, min(780, root.winfo_screenheight() - 100))
        root.minsize(min(650, width), min(540, height))
        root.geometry(f'{width}x{height}')
        root.protocol('WM_DELETE_WINDOW', self.close)

        # Keep the action buttons visible on small displays and with Windows scaling.
        footer = ttk.Frame(root, padding=(16, 8, 16, 12))
        footer.pack(side='bottom', fill='x')
        status_label = ttk.Label(footer, textvariable=self.status, wraplength=max(200, width - 32))
        status_label.pack(anchor='w', pady=(0, 8))
        footer.bind('<Configure>', lambda event: status_label.configure(wraplength=max(200, event.width - 32)))
        self.progress = ttk.Progressbar(footer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 8))
        buttons = ttk.Frame(footer)
        buttons.pack(fill='x')
        self.save_button = ttk.Button(buttons, text='Configure online hosting', command=self.start)
        self.save_button.pack(side='left')
        self.controls.append(self.save_button)
        self.copy_button = ttk.Button(buttons, text='Copy instructions', command=self.copy_result, state='disabled')
        self.copy_button.pack(side='left', padx=8)
        self.close_button = ttk.Button(buttons, text='Close', command=self.close)
        self.close_button.pack(side='right')
        self.controls.append(self.close_button)

        outer = ttk.Frame(root, padding=(12, 12, 12, 0))
        outer.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        form = ttk.Frame(self.canvas, padding=(4, 4, 12, 8))
        window_id = self.canvas.create_window((0, 0), window=form, anchor='nw')
        form.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))

        def resize(event):
            self.canvas.itemconfigure(window_id, width=event.width)
            for label in self.wrap_labels:
                label.configure(wraplength=max(360, event.width - 56))

        self.canvas.bind('<Configure>', resize)
        root.bind('<MouseWheel>', self.scroll)
        root.bind('<Control-Return>', lambda _: self.start())
        root.bind('<Escape>', lambda _: self.close())

        ttk.Label(form, text='Set up encrypted online hosting', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        self.description(form, 'Stop the world server before saving. This setup creates or imports its TLS certificate '
                         'and prepares the connection instructions for your players.').pack(anchor='w', pady=(6, 12))

        address = ttk.LabelFrame(form, text='1. Address players will connect to', padding=10)
        address.pack(fill='x', pady=4)
        self.description(address, 'Public hostname or IP address — for example, play.example.com').pack(anchor='w')
        self.host_entry = ttk.Entry(address, textvariable=self.host, width=55)
        self.host_entry.pack(fill='x', pady=(6, 4))
        self.host_entry.bind('<Control-a>', self.select_all)
        self.controls.append(self.host_entry)
        self.description(address, 'Enter the host only, without https://, a port, or a path. The certificate must match '
                         'this exact address. If your public IP changes, use a hostname you keep updated.').pack(anchor='w')

        certificate = ttk.LabelFrame(form, text='2. Certificate', padding=10)
        certificate.pack(fill='x', pady=(8, 4))
        generate = ttk.Radiobutton(certificate, text='Create a private certificate for this world', variable=self.mode,
                                   value='generate', command=self.update_mode)
        generate.pack(anchor='w')
        self.controls.append(generate)
        self.description(certificate, 'Each player must explicitly trust the public certificate on their Windows account '
                         'using the generated connection kit. Verify its fingerprint with the host first. '
                         'Keep the private key on the server.').pack(anchor='w', padx=(24, 0), pady=(3, 10))
        existing = ttk.Radiobutton(certificate, text='Import an existing certificate and private key', variable=self.mode,
                                   value='import', command=self.update_mode)
        existing.pack(anchor='w')
        self.controls.append(existing)
        self.description(certificate, 'Use a valid certificate chain issued for this address and its matching private key '
                         'in PEM format. A certificate trusted by Windows needs no private-certificate trust step.').pack(
                             anchor='w', padx=(24, 0), pady=(3, 6))
        files = ttk.Frame(certificate)
        files.pack(fill='x', padx=(24, 0))
        files.columnconfigure(1, weight=1)
        self.file_field(files, 0, 'Certificate / chain', self.certificate, False)
        self.file_field(files, 1, 'Private key', self.private_key, True)

        self.description(form, 'Configuration: ' + str(self.path)).pack(anchor='w', pady=(8, 6))
        result_frame = ttk.LabelFrame(form, text='Connection instructions and saved paths', padding=8)
        result_frame.pack(fill='both', expand=True, pady=(4, 4))
        result_scroll = ttk.Scrollbar(result_frame, orient='vertical')
        result_scroll.pack(side='right', fill='y')
        self.output = tk.Text(result_frame, height=9, width=60, wrap='word', font=('Consolas', 10),
                              state='disabled', yscrollcommand=result_scroll.set)
        self.output.pack(fill='both', expand=True)
        result_scroll.configure(command=self.output.yview)
        self.set_output('After saving, the exact certificate and connection-kit paths will appear here.\n\n'
                        'Internet access also needs the game TCP port allowed through the host firewall and forwarded '
                        'by the router, plus a reachable public address. This setup does not change your router.')
        self.update_mode()
        self.host_entry.focus_set()
        self.poll_id = root.after(100, self.poll)
        root.bind('<Destroy>', self.on_destroy, add='+')

    def description(self, parent, text):
        label = ttk.Label(parent, text=text, wraplength=780, justify='left')
        self.wrap_labels.append(label)
        return label

    def file_field(self, parent, row: int, label: str, variable, private: bool):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky='ew', pady=4)
        entry.bind('<Control-a>', self.select_all)
        button = ttk.Button(parent, text='Browse...', command=lambda: self.browse(variable, private))
        button.grid(row=row, column=2, padx=(8, 0), pady=4)
        self.controls.extend((entry, button))
        self.import_controls.extend((entry, button))

    @staticmethod
    def select_all(event):
        event.widget.selection_range(0, 'end')
        event.widget.icursor('end')
        return 'break'

    def scroll(self, event):
        if event.widget is self.output:
            return
        self.canvas.yview_scroll(-int(event.delta / 120), 'units')

    def browse(self, variable, private: bool):
        if self.busy or self.mode.get() != 'import':
            return
        filename = filedialog.askopenfilename(parent=self.root,
            title='Select matching private key' if private else 'Select certificate / chain',
            filetypes=[('PEM private key', '*.key *.pem')] if private else
                      [('PEM certificate / chain', '*.crt *.pem *.cer')],
            initialdir=str(self.path.parent))
        if filename:
            variable.set(filename)

    def update_mode(self):
        enabled = not self.busy and self.mode.get() == 'import'
        self.save_button.configure(text=('Create certificate and configure hosting' if self.mode.get() == 'generate'
                                         else 'Import certificate and configure hosting'))
        for control in self.import_controls:
            control.state(['!disabled' if enabled else 'disabled'])

    def collect(self) -> SetupOptions:
        generate = self.mode.get() == 'generate'
        certificate = self.certificate.get().strip()
        private_key = self.private_key.get().strip()
        if not generate and (not certificate or not private_key):
            raise SetupError('Choose both the existing certificate / chain and its matching private key.')
        options = SetupOptions(host=self.host.get().strip(), generate=generate,
                               certificate=Path(certificate) if not generate else None,
                               private_key=Path(private_key) if not generate else None)
        options.validate()
        return options

    def start(self):
        if self.busy:
            return
        try:
            options = self.collect()
        except SetupError as exc:
            messagebox.showerror('Check online-hosting fields', str(exc), parent=self.root)
            return
        confirmation = ('Stop the world server before continuing.\n\n'
                        'Save the TLS configuration for ' + options.validate() + '?\n\n'
                        'Configuration: ' + str(self.path))
        if options.generate:
            confirmation += ('\n\nA private certificate will be created. Every player must explicitly trust its public '
                             'certificate and verify its fingerprint with you before connecting. Only share the '
                             'connection kit; keep the private key on this server.')
        if not messagebox.askokcancel('Save online-hosting configuration?', confirmation, parent=self.root):
            return
        self.busy = True
        self.success = False
        for control in self.controls:
            control.state(['disabled'])
        self.copy_button.state(['disabled'])
        self.progress.start(15)
        self.status.set('Preparing and validating TLS files. Please keep this window open...')
        self.set_output('Preparing the certificate, server configuration and connection kit...')

        # Pass only immutable options and paths to the worker, never Tk variables.
        def work():
            try:
                result = configure(options, self.path)
                self.events.put(('saved', result.message()))
            except SetupError as exc:
                self.events.put(('error', str(exc)))
            except Exception as exc:
                self.events.put(('error', 'Unexpected online-hosting setup failure [' + type(exc).__name__ +
                                 ']. Configuration may be incomplete. Run Check Configuration before starting the world.'))

        threading.Thread(target=work, name='NXT-Online-Setup', daemon=False).start()

    def set_output(self, text: str):
        self.result_text = text
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', text)
        self.output.configure(state='disabled')
        self.output.yview_moveto(0)

    def copy_result(self):
        if not self.busy and self.result_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.result_text)
            self.status.set('Instructions copied. Share the connection kit; keep server private keys private.')

    def poll(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                self.busy = False
                self.progress.stop()
                for control in self.controls:
                    control.state(['!disabled'])
                self.update_mode()
                self.copy_button.state(['!disabled'])
                self.set_output(text)
                if kind == 'saved':
                    self.success = True
                    self.status.set('Online-hosting configuration saved. Follow the connection instructions below, then start the world.')
                    self.close_button.configure(text='Done')
                    self.canvas.yview_moveto(1)
                    self.close_button.focus_set()
                else:
                    self.status.set('Setup did not complete. Review the error below and correct the fields.')
                    messagebox.showerror('Online-hosting setup - action needed', text, parent=self.root)
        except queue.Empty:
            pass
        self.poll_id = self.root.after(100, self.poll)

    def on_destroy(self, event):
        if event.widget is self.root:
            try:
                self.root.after_cancel(self.poll_id)
            except tk.TclError:
                pass

    def close(self):
        if self.busy:
            self.root.bell()
            return
        self.root.destroy()


def run_gui(config_path: Path) -> int:
    if tk is None:
        raise GuiUnavailable('Tk is unavailable; use console setup.')
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    try:
        root = tk.Tk()
    except tk.TclError:
        raise GuiUnavailable('No graphical display; use console setup.') from None
    try:
        window = SetupWindow(root, config_path)
        root.mainloop()
        return 0 if window.success else 1
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
