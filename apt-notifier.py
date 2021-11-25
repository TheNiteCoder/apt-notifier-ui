
from apt.cache import LockFailedException
from apt_pkg import Package
import gi
import apt
import threading, sys
gi.require_version('Gtk', '3.0')

from gi.repository import Gtk, GLib

def async_call(f, on_done=None):
    if not on_done:
        on_done = lambda r, e: None

    def do_call():
        result = None
        error = None

        #try:
        result = f()
        #except Exception as err:
        #    error = err
        error = None

        GLib.idle_add(lambda: on_done(result, error))
    thread = threading.Thread(target = do_call)
    thread.start()

class APTAquireProgressBar(apt.progress.base.AcquireProgress):
    def __init__(self, progressbar):
        super().__init__()
        self.progressbar = progressbar
    def done(self, item):
        print(f'finnished {item.description}')
        self.progressbar.set_fraction(1.0)
        self.progressbar.set_text(item.description)
    def update(self, percent=None):
        print(f'{percent if percent else ""}')
        if percent is not None:
            self.progressbar.set_text(f'{self.op}: {self.subop}')
            self.progressbar.set_fraction(percent / 100)

class APTOperationProgress(apt.progress.base.OpProgress):
    def __init__(self, progress_bar=None):
        super().__init__()
        self.progress_bar = progress_bar
    def done(self):
        if self.progress_bar:
            self.progress_bar.set_fraction(1.0)
    def update(self, percent=None):
        print(f"{self.op}{'/' + self.subop if self.subop else ''}: {percent if percent else '...'}")
        if self.progress_bar:
            self.progress_bar.set_text(f'{self.op}/{self.subop}')
        if percent and self.progress_bar:
            self.progress_bar.set_fraction(percent / 100)

class APTInstallProgress(apt.progress.base.InstallProgress):
    def __init__(self, progres_bar=None):
        super().__init__()
        self.progress_bar = progres_bar
    def status_change(self, pkg, percent, status):
        if self.progress_bar:
            self.progress_bar.set_text(f'{pkg}: {status}')
            self.progress_bar.set_fraction(percent / 100)
    def conffile(self, current, new):
        pass
    def error(self, pkg, errormsg):
        pass

class APT:
    COLUMN_UPGRADING = 0
    COLUMN_PACKAGE_NAME = 1
    COLUMN_PACKAGE = 2
    COLUMN_VERSION = 3
    def __init__(self):
        self.package_model = Gtk.ListStore(bool, str, str, str)
        self.apt_cache = apt.Cache(APTOperationProgress())
    def update(self, progress_bar):
        print('Running update...')
        try:
            self.apt_cache.update(APTAquireProgressBar(progress_bar))
            self.apt_cache.open(APTOperationProgress(progress_bar))
            self.apt_cache.upgrade()
        except apt.cache.LockFailedException:
            print("Can't get lock")
    def upgrade(self, progress_bar):
        print('Running upgrade...')
        try:
            self.apt_cache.commit(APTAquireProgressBar(progress_bar), APTInstallProgress(progress_bar))
        except apt.cache.LockFailedException:
            print("Can't get lock")
        self.populate_packages(progress_bar)
    def populate_packages(self, progress_bar):
        print('Populating with upgradable packages')
        self.update(progress_bar)
        self.package_model.clear()
        changes = self.apt_cache.get_changes()
        for package in changes:
            if package.marked_upgrade:
                self.package_model.append([True, package.shortname, package.fullname, package.candidate.version])
    def cleanup(self):
        self.apt_cache.close()

class UpdaterWindow(Gtk.Dialog):
    def __init__(self, apt, root=None):
        super().__init__(root)
        self.apt = apt
        self.set_default_size(400, 150)
        self.package_model = self.apt.package_model
        self.package_stack = Gtk.Stack()
        self.tree = Gtk.TreeView(model=self.package_model)
        self.no_packages_label = Gtk.Label("No Packages to Upgrade")
        self.package_stack.add(self.tree)
        self.package_stack.add(self.no_packages_label)
        #self.toggle_renderer = Gtk.CellRendererToggle()
        #self.toggle_renderer.connect("toggled", self.handle_toggle)
        #self.tree.append_column(Gtk.TreeViewColumn("Upgrade", self.toggle_renderer, active=self.COLUMN_UPGRADING))
        self.tree.append_column(Gtk.TreeViewColumn("Package", Gtk.CellRendererText(), text=APT.COLUMN_PACKAGE_NAME))
        self.tree.append_column(Gtk.TreeViewColumn("Version", Gtk.CellRendererText(), text=APT.COLUMN_VERSION))
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.get_content_area().pack_start(vbox, True, True, 0)
        self.progress_bar = Gtk.ProgressBar()
        vbox.pack_start(self.package_stack, True, True, 3)
        vbox.pack_start(self.progress_bar, False, False, 0)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        vbox.pack_start(hbox, False, False, 0)
        self.update_button = Gtk.Button.new_with_label("Update")
        self.update_button.connect("clicked", lambda x: async_call(lambda: self.apt.upgrade(self.progress_bar), lambda r, x: self.after_populate()))
        self.cancel_button = Gtk.Button.new_with_label("Close")
        self.cancel_button.connect("clicked", lambda x: self.hide())
        hbox.pack_start(self.update_button, True, True, 0)
        hbox.pack_start(self.cancel_button, True, True, 0)
        self.after_populate()
        async_call(lambda: self.apt.populate_packages(self.progress_bar), lambda x, e: self.after_populate())
    def after_populate(self):
        if len(self.package_model) > 0:
            self.update_button.set_sensitive(True)
            self.package_stack.set_visible_child(self.tree)
        else:
            self.update_button.set_sensitive(False)
            self.package_stack.set_visible_child(self.no_packages_label)
    def handle_toggle(self, cell, path_string, data=None):
        path = Gtk.TreePath.new_from_string(path_string)
        model_iter = self.package_model.get_iter(path)
        value = not self.package_model.get_value(model_iter, APT.COLUMN_UPGRADING)
        self.package_model.set_value(model_iter, APT.COLUMN_UPGRADING, value)
        package_name = self.package_model.get_value(model_iter, APT.COLUMN_PACKAGE)
        package = self.apt_cache[package_name]
        package.mark_upgrade(value)

Apt = APT()

window = UpdaterWindow(Apt)
window.connect('destroy', Gtk.main_quit)
window.connect('destroy', lambda x: Apt.cleanup())
window.show_all()

Gtk.main()

