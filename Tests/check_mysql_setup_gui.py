"""Optional real-Tk widget/worker checks; fake DB connector, no MySQL daemon.
Run on a desktop: python Tests/check_mysql_setup_gui.py
Linux headless: xvfb-run -a python Tests/check_mysql_setup_gui.py
Not imported by unittest discover, because Tcl/Tk is an optional build dependency.
"""
from pathlib import Path
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
sys.path.insert(0, str(ROOT / 'Tests'))
import tkinter as tk
import setup_mysql as core
import setup_mysql_gui as gui
from test_mysql_setup import FakeDatabase


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'config.ini'
        self.path.write_bytes((ROOT / 'Server/config.ini').read_bytes())
        self.root = tk.Tk()
        self.window = gui.SetupWindow(self.root, self.path)
        self.root.update()
        self.errors = []
        self.infos = []
        self.patches = [patch.object(gui.messagebox, 'showerror', side_effect=lambda title, msg, **k: self.errors.append(msg)),
                        patch.object(gui.messagebox, 'showinfo', side_effect=lambda title, msg, **k: self.infos.append(msg)),
                        patch.dict(os.environ, {}, clear=True)]
        for p in self.patches:
            p.start()
    def tearDown(self):
        self.root.destroy()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()
    def finish(self):
        deadline = time.monotonic() + 4
        while self.window.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.window.busy, 'worker did not finish')
        self.root.update()
    def test_masking_show_toggle_and_exact_input(self):
        entry = self.window.entries['admin_password']
        text = ' Päss!%&?123 '
        entry.insert(0, text)
        self.assertEqual(entry.get(), text)
        self.assertEqual(str(entry.cget('show')), '*')
        self.window.show_passwords.set(True)
        self.window.toggle_passwords()
        self.assertEqual(str(entry.cget('show')), '')
        self.window.show_passwords.set(False)
        self.window.toggle_passwords()
        self.assertEqual(self.window.collect().admin_password, text)
    def test_clipboard_paste_and_select_all_are_native(self):
        text = 'Paste!%&?123'
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        entry = self.window.entries['admin_password']
        entry.focus_force()
        entry.event_generate('<<Paste>>')
        self.root.update()
        self.assertEqual(entry.get(), text)
        self.window.select_all(entry)
        self.assertTrue(entry.selection_present())
        entry.delete('sel.first', 'sel.last')
        self.assertEqual(entry.get(), '')
    def test_blank_test_has_no_changes_and_does_not_mark_saved(self):
        before = self.path.read_bytes()
        db = FakeDatabase()
        with patch.object(gui, 'test_administrator', side_effect=lambda options, path: core.test_administrator(options, path, connect=db.connect)):
            self.window.start('test')
            self.assertTrue(self.window.busy)
            self.assertTrue(self.window.entries['admin_password'].instate(['disabled']))
            self.finish()
        self.assertFalse(self.window.success)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.errors, [])
        self.assertTrue(self.infos)
    def test_wrong_password_can_be_corrected_without_restarting(self):
        db = FakeDatabase(root_password='CorrectExisting!123')
        before = self.path.read_bytes()
        with patch.object(gui, 'test_administrator', side_effect=lambda options, path: core.test_administrator(options, path, connect=db.connect)):
            self.window.vars['admin_password'].set('WrongPassword!123')
            self.window.start('test')
            self.finish()
            self.assertEqual(len(self.errors), 1)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertTrue(self.window.entries['admin_password'].instate(['!disabled']))
            self.window.vars['admin_password'].set('CorrectExisting!123')
            self.window.start('test')
            self.finish()
        self.assertEqual(len(self.errors), 1)
        self.assertEqual(len(self.infos), 1)
    def test_form_save_end_to_end_fake_database(self):
        db = FakeDatabase(root_password='ExistingAdmin!123')
        self.window.vars['admin_password'].set('ExistingAdmin!123')
        self.window.vars['application_password'].set('NewNxt%!?&Password123')
        self.window.vars['confirm'].set('NewNxt%!?&Password123')
        with patch.object(gui, 'provision', side_effect=lambda options, path, progress: core.provision(options, path, connect=db.connect, progress=progress)):
            self.window.start('save')
            self.finish()
        self.assertTrue(self.window.success)
        self.assertEqual(self.errors, [])
        self.assertEqual(core.load_config(self.path).get('database', 'password'), 'NewNxt%!?&Password123')
        self.assertNotIn('ExistingAdmin!123', self.path.read_text())
        for key in ('admin_password', 'application_password', 'confirm'):
            self.assertEqual(self.window.vars[key].get(), '')
    def test_custom_confirmation_and_validation_before_worker(self):
        self.window.vars['application_password'].set('NotMatching!123')
        self.window.start('save')
        self.assertFalse(self.window.busy)
        self.assertEqual(len(self.errors), 1)
    def test_close_blocked_while_worker_is_active(self):
        self.window.busy = True
        self.window.close()
        self.assertTrue(self.root.winfo_exists())
        self.window.busy = False
    def test_footer_controls_reachable_at_small_resolution(self):
        self.root.geometry('680x550')
        self.root.update()
        button = self.window.close_button
        self.assertGreaterEqual(button.winfo_rooty(), self.root.winfo_rooty())
        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), self.root.winfo_rooty() + self.root.winfo_height())
        self.assertGreater(self.window.canvas.bbox('all')[3], self.window.canvas.winfo_height())


if __name__ == '__main__':
    unittest.main(verbosity=2)
