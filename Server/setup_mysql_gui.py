"""Native Tk password-entry form. Worker threads never access Tk objects."""
from __future__ import annotations
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from setup_mysql import SetupError, SetupOptions, SETUP_VERSION, defaults, load_config, provision, test_administrator


class GuiUnavailable(RuntimeError):
    pass


class SetupWindow:
    def __init__(self, root: tk.Tk, config_path: Path):
        self.root = root
        self.path = config_path
        self.busy = False
        self.success = False
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.controls: list = []
        self.password_entries: list = []
        self.vars: dict[str, tk.StringVar] = {}
        self.show_passwords = tk.BooleanVar(root, False)
        self.wildcard = tk.BooleanVar(root, False)
        config = defaults(load_config(config_path))
        root.title('Pokemon NXT MMO - MySQL Setup ' + SETUP_VERSION)
        root.minsize(660, 530)
        root.geometry('840x760')
        root.protocol('WM_DELETE_WINDOW', self.close)
        # Scrollable body keeps the buttons reachable on small/scaled displays.
        outer = ttk.Frame(root, padding=12)
        outer.pack(fill='both', expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        form = ttk.Frame(canvas, padding=(4, 4, 12, 8))
        self.canvas = canvas
        window_id = canvas.create_window((0, 0), window=form, anchor='nw')
        form.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window_id, width=event.width))
        root.bind('<MouseWheel>', lambda event: canvas.yview_scroll(-int(event.delta / 120), 'units'))
        ttk.Label(form, text='Connect MySQL. Create the separate NXT account.', font=('Segoe UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(form, text='Start MySQL (or XAMPP > MySQL > Start) first. Stop the NXT world before saving.\n'
                  'This setup does NOT create/reset root\'s password or modify another game\'s database.',
                  wraplength=700).pack(anchor='w', pady=(6, 10))
        admin = ttk.LabelFrame(form, text='1. EXISTING MySQL administrator login', padding=10)
        admin.pack(fill='x', pady=4)
        self.field(admin, 'host', 'MySQL host / IP', config.host, 0)
        self.field(admin, 'port', 'MySQL port', str(config.port), 1)
        self.field(admin, 'admin_username', 'Existing admin username', 'root', 2)
        self.field(admin, 'admin_password', 'Existing admin password', '', 3, secret=True)
        ttk.Label(admin, text='Type/paste the password ALREADY set for this MySQL account. Not your Windows password.\n'
                  'Leave blank only when that existing account has no password. Dots show your typing.',
                  wraplength=650).grid(row=4, column=0, columnspan=2, sticky='w', pady=(4, 6))
        show = ttk.Checkbutton(admin, text='Show passwords on screen (turn off before screen-sharing)',
                               variable=self.show_passwords, command=self.toggle_passwords)
        show.grid(row=5, column=0, columnspan=2, sticky='w')
        self.controls.append(show)
        test = ttk.Button(admin, text='Test administrator login (no changes)', command=lambda: self.start('test'))
        test.grid(row=6, column=0, columnspan=2, sticky='w', pady=(8, 0))
        self.controls.append(test)
        app = ttk.LabelFrame(form, text='2. Separate NXT application account', padding=10)
        app.pack(fill='x', pady=(8, 4))
        self.field(app, 'database', 'NXT database name', config.database, 0)
        self.field(app, 'username', 'NXT application username', config.username, 1)
        self.field(app, 'account_host', 'World host as MySQL sees it', 'localhost', 2)
        ttk.Label(app, text='Keep localhost when MySQL and the world service run on this PC.',
                  wraplength=650).grid(row=3, column=0, columnspan=2, sticky='w')
        self.field(app, 'application_password', 'NXT application password', '', 4, secret=True)
        self.field(app, 'confirm', 'Confirm custom password', '', 5, secret=True)
        ttk.Label(app, text='Leave BOTH blank to reuse the configured password or generate a strong new one.\n'
                  'A custom application password needs 12-256 characters. Existing account passwords are never reset.',
                  wraplength=650).grid(row=6, column=0, columnspan=2, sticky='w', pady=(4, 4))
        wildcard = ttk.Checkbutton(app, text='Advanced: approve a % wildcard account host (not needed locally)', variable=self.wildcard)
        wildcard.grid(row=7, column=0, columnspan=2, sticky='w')
        self.controls.append(wildcard)
        ttk.Label(form, text='Target config: ' + str(config_path), wraplength=700).pack(anchor='w', pady=(8, 0))
        footer = ttk.Frame(root, padding=(16, 8, 16, 12))
        footer.pack(fill='x')
        self.status = tk.StringVar(root, 'Ready. Enter your existing administrator password, or leave it empty only if none is set.')
        ttk.Label(footer, textvariable=self.status, wraplength=750).pack(anchor='w', pady=(0, 8))
        self.progress = ttk.Progressbar(footer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 8))
        buttons = ttk.Frame(footer)
        buttons.pack(fill='x')
        save = ttk.Button(buttons, text='Configure NXT database and save', command=lambda: self.start('save'))
        save.pack(side='left')
        self.controls.append(save)
        self.close_button = ttk.Button(buttons, text='Close', command=self.close)
        self.close_button.pack(side='right')
        self.controls.append(self.close_button)
        self.vars['admin_password'].set('')
        self.entries['admin_password'].focus_set()
        self.poll_id = root.after(100, self.poll)
        root.bind('<Destroy>', self.on_destroy, add='+')

    def field(self, parent, key: str, label: str, value: str, row: int, *, secret: bool = False):
        if not hasattr(self, 'entries'):
            self.entries = {}
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
        var = tk.StringVar(self.root, value)
        entry = ttk.Entry(parent, textvariable=var, show='*' if secret else '', width=40)
        entry.grid(row=row, column=1, sticky='ew', pady=4)
        # Entry widgets retain native editing, Ctrl+V/Shift+Insert and selection.
        entry.bind('<Control-a>', lambda event: self.select_all(event.widget))
        self.vars[key] = var
        self.entries[key] = entry
        self.controls.append(entry)
        if secret:
            self.password_entries.append(entry)

    @staticmethod
    def select_all(widget):
        widget.selection_range(0, 'end')
        widget.icursor('end')
        return 'break'

    def toggle_passwords(self):
        for entry in self.password_entries:
            entry.configure(show='' if self.show_passwords.get() else '*')

    def collect(self, *, administrator_only: bool = False) -> SetupOptions:
        try:
            port = int(self.vars['port'].get().strip())
        except ValueError:
            raise SetupError('MySQL port must be a whole number, normally 3306.') from None
        custom = self.vars['application_password'].get()
        if not administrator_only and custom != self.vars['confirm'].get():
            raise SetupError('The NXT application password and confirmation do not match. Leave BOTH blank to generate/reuse automatically.')
        options = SetupOptions(host=self.vars['host'].get().strip(), port=port,
                               database=self.vars['database'].get().strip(), username=self.vars['username'].get().strip(),
                               account_host=self.vars['account_host'].get().strip(), admin_username=self.vars['admin_username'].get().strip(),
                               admin_password=self.vars['admin_password'].get(), application_password=custom,
                               allow_wildcard=self.wildcard.get())
        options.validate(administrator_only=administrator_only)
        return options

    def start(self, action: str):
        if self.busy:
            return
        try:
            options = self.collect(administrator_only=action == 'test')
        except SetupError as exc:
            messagebox.showerror('Check setup fields', str(exc), parent=self.root)
            return
        self.busy = True
        self.show_passwords.set(False)
        self.toggle_passwords()
        for control in self.controls:
            control.state(['disabled'])
        self.progress.start(15)
        self.status.set('Checking MySQL... The window stays responsive; credentials are not logged.')
        # Immutable plain options cross the thread boundary; never StringVars.
        def work():
            try:
                result = (test_administrator(options, self.path) if action == 'test' else
                          provision(options, self.path, progress=lambda text: self.events.put(('progress', text))))
                self.events.put(('tested' if action == 'test' else 'saved', result))
            except SetupError as exc:
                self.events.put(('error', str(exc)))
            except Exception as exc:
                self.events.put(('error', f'Unexpected setup failure [{type(exc).__name__}]. No raw credential-bearing error was displayed.'))
        # Do not tear down mid-DDL; closing is disabled until the bounded calls end.
        threading.Thread(target=work, name='NXT-MySQL-Setup', daemon=False).start()

    def poll(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                self.status.set(text)
                if kind == 'progress':
                    continue
                self.busy = False
                self.progress.stop()
                for control in self.controls:
                    control.state(['!disabled'])
                if kind == 'error':
                    self.status.set('Setup did not complete. Correct the fields and try again; config.ini was not replaced by a failed login.')
                    messagebox.showerror('MySQL setup - action needed', text + '\n\nExisting root passwords are never changed. '
                                         'Account/database creation can partly succeed before a later error; existing records are not deleted.', parent=self.root)
                    self.entries['admin_password'].focus_set()
                elif kind == 'tested':
                    messagebox.showinfo('Administrator login OK', text, parent=self.root)
                else:
                    self.success = True
                    for key in ('admin_password', 'application_password', 'confirm'):
                        self.vars[key].set('')
                    messagebox.showinfo('NXT MySQL configured', text, parent=self.root)
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
        for key in ('admin_password', 'application_password', 'confirm'):
            self.vars[key].set('')
        self.root.destroy()


def run_gui(config_path: Path) -> int:
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise GuiUnavailable('No graphical display') from None
    try:
        window = SetupWindow(root, config_path)
        root.mainloop()
        return 0 if window.success else 1
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
