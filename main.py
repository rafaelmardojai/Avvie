
# Load Gtk
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk, Gdk, Gio, Adw, GLib, Notify
import os
import sys
import math
import gi
import cairo
import urllib.parse
import subprocess
import piexif
import json
from PIL import Image, ImageFilter

app_title = 'Avvie'
app_id = "com.github.taiko2k.avvie"
version = "2.0"

# App background colour
background_color = (0.15, 0.15, 0.15)

# Load json config file
config_folder = os.path.join(GLib.get_user_config_dir(), app_id)
config_file = os.path.join(config_folder, "avvie.json")

if not os.path.exists(config_folder):
    os.makedirs(config_folder)

config = {}
if os.path.isfile(config_file):
    with open(config_file) as f:
        config = json.load(f)
        print(f"Loaded config {config_file}")

# Add
Notify.init(app_title)
notify = Notify.Notification.new(app_title, "Image file exported to Downloads.")
notify_invalid_output = Notify.Notification.new(app_title, "Could not locate output folder!")

# Is this defined somewhere in Gtk?
TARGET_TYPE_URI_LIST = 80


# Add open file action to notification
def open_encode_out(notification, action, data):
    subprocess.call(["xdg-open", picture.last_saved_location])


notify.add_action(
    "action_click",
    "Open output folder",
    open_encode_out,
    None
)


def point_in_rect(rx, ry, rw, rh, px, py):
    return ry < py < ry + rh and rx < px < rx + rw


# Get distance between two points (pythagoras)
def point_prox(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


# class FileChooserWithImagePreview(Gtk.FileChooserNative):
#     resize_to = (256, 256)
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#
#         self.preview_widget = Gtk.Image()
#         self.set_preview_widget(self.preview_widget)
#         self.connect(
#             "update-preview",
#             self.update_preview,
#             self.preview_widget
#         )
#
#     def update_preview(self, dialog, preview_widget):
#         filename = self.get_preview_filename()
#         try:
#             pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename, *self.resize_to)
#             preview_widget.set_from_pixbuf(pixbuf)
#             have_preview = True
#         except:
#             have_preview = False
#
#         self.set_preview_widget_active(have_preview)


class Picture:
    def __init__(self):
        self.source_image = None
        self.surface = None
        self.source_w = 0
        self.source_h = 0
        self.display_w = 0
        self.display_h = 0
        self.display_x = 0
        self.display_y = 0
        self.ready = False
        self.lock_ratio = True

        self.rec_x = 10
        self.rec_y = 10
        self.rec_w = 250
        self.rec_h = 250

        self.drag_start_position = (0, 0)

        self.dragging_center = False
        self.dragging_tr = False
        self.dragging_tl = False
        self.dragging_bl = False
        self.dragging_br = False
        self.original_position = (0, 0)
        self.original_drag_size = (0, 0)

        self.scale_factor = 1
        self.bounds = (500, 500)

        self.surface184 = None

        self.file_name = ""
        self.loaded_fullpath = ""
        self.download_folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        self.pictures_folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        self.export_setting = "pictures"
        if "output-mode" in config:
            self.export_setting = config["output-mode"]
        self.last_saved_location = ""

        self.sharpen = False
        self.export_constrain = None
        self.crop_ratio = (1, 1)
        self.png = False
        self.crop = True
        self.slow_drag = False
        self.circle = False
        self.rotation = 0
        self.flip_hoz = False
        self.flip_vert = False
        self.gray = False
        self.discard_exif = False
        self.exif = None

        self.corner_hot_area = 60
        self.all_drag_min = 400

        self.thumbs = [184, 64, 32]

        self.thumb_cache_key = ()
        self.thumb_cache_img = None

        # Load thumbnail sizes from saved config
        if "thumbs" in config:
            try:
                thumbs = config["thumbs"]
                for size in thumbs:
                    assert type(size) is int
                self.thumbs = thumbs
            except:
                print("Error reading config")
                raise

        self.thumb_surfaces = {}

    def test_br(self, x, y):
        rx, ry, rw, rh = self.get_display_rect()

        tx = rx + rw
        ty = ry + rh
        tw = self.corner_hot_area
        th = self.corner_hot_area

        tx -= self.corner_hot_area // 2
        ty -= self.corner_hot_area // 2

        if tx < rx + (rw // 3):
            tx = rx + (rw // 3)

        if ty < ry + (rh // 3):
            ty = ry + (rh // 3)

        return point_in_rect(picture.display_x + tx, picture.display_y + ty, tw, th, x, y)

    def test_tl(self, x, y):
        rx, ry, rw, rh = self.get_display_rect()

        tx = rx
        ty = ry
        tw = self.corner_hot_area
        th = self.corner_hot_area

        tx -= self.corner_hot_area // 2
        ty -= self.corner_hot_area // 2

        if ty + th > ry + rh // 3:
            ty = (ry + rh // 3) - th

        if tx + tw > rx + (rw // 3):
            tx = (rx + (rw // 3)) - tw

        return point_in_rect(picture.display_x + tx, picture.display_y + ty, tw, th, x, y)

    def test_bl(self, x, y):
        rx, ry, rw, rh = self.get_display_rect()
        tx = rx
        ty = ry + rh
        tw = self.corner_hot_area
        th = self.corner_hot_area

        tx -= self.corner_hot_area // 2
        ty -= self.corner_hot_area // 2

        if ty < ry + (rh // 3):
            ty = ry + (rh // 3)

        if tx + tw > rx + (rw // 3):
            tx = (rx + (rw // 3)) - tw

        return point_in_rect(picture.display_x + tx, picture.display_y + ty, tw, th, x, y)

    def test_tr(self, x, y):
        rx, ry, rw, rh = self.get_display_rect()
        tx = rx + rw
        ty = ry
        tw = self.corner_hot_area
        th = self.corner_hot_area

        tx -= self.corner_hot_area // 2
        ty -= self.corner_hot_area // 2

        if ty + th > ry + rh // 3:
            ty = (ry + rh // 3) - th

        if tx < rx + (rw // 3):
            tx = rx + (rw // 3)

        return point_in_rect(picture.display_x + tx, picture.display_y + ty, tw, th, x, y)

    def test_center_start_drag(self, x, y):

        rx, ry, rw, rh = self.get_display_rect()

        return point_in_rect(picture.display_x + rx, picture.display_y + ry, rw, rh, x, y)
        # border = self.corner_hot_area / 2
        # if x < self.display_x + rx + border:
        #     return False
        # if y < self.display_y + ry + border:
        #     return False
        # if x > self.display_x + rx + rw - border:
        #     return False
        # if y > self.display_y + ry + rh - border:
        #     return False
        # return True

    def apply_filters(self, im):

        if self.sharpen:
            im = im.filter(ImageFilter.UnsharpMask(radius=0.35, percent=150, threshold=0))

        return im

    def gen_thumbnails(self, hq=False):

        # if self.rotation and not hq:
        #     return

        key = (self.source_image, self.gray, self.flip_hoz, self.flip_vert, self.rotation)
        if self.source_image and self.thumb_cache_key == key:
            im = self.thumb_cache_img
        else:
            self.thumb_cache_key = key

            im = self.source_image
            if not im:
                return

            if self.gray:
                im = im.convert("L")
                im = im.convert("RGB")

            if self.flip_hoz:
                im = im.transpose(method=Image.FLIP_LEFT_RIGHT)
            if self.flip_vert:
                im = im.transpose(method=Image.FLIP_TOP_BOTTOM)

            if self.rotation:
                im = im.rotate(self.rotation, expand=True, resample=Image.BICUBIC)

            self.thumb_cache_img = im

        if self.crop:
            cr = im.crop((self.rec_x, self.rec_y, self.rec_x + self.rec_w, self.rec_y + self.rec_h))
        else:
            cr = im.copy()

        cr.load()

        for size in self.thumbs:
            if not hq:
                cr.thumbnail((size, size), Image.NEAREST)  # BILINEAR
            else:
                cr.thumbnail((size, size), Image.ANTIALIAS)

            w, h = cr.size

            if "A" not in cr.getbands():
                cr.putalpha(int(1 * 256.0))

            cr = self.apply_filters(cr)

            by = cr.tobytes("raw", "BGRa")
            arr = bytearray(by)
            self.thumb_surfaces[size] = cairo.ImageSurface.create_for_data(
                arr, cairo.FORMAT_ARGB32, w, h
            )

    def reload(self, keep_rect=False):

        im = self.source_image.copy()
        im.load()

        if self.flip_hoz:
            im = im.transpose(method=Image.FLIP_LEFT_RIGHT)
        if self.flip_vert:
            im = im.transpose(method=Image.FLIP_TOP_BOTTOM)

        if self.rotation:
            im = im.rotate(self.rotation, expand=True, resample=Image.NEAREST)  # , resample=0)

        w, h = im.size
        self.source_w, self.source_h = w, h
        self.display_w, self.display_h = w, h
        self.display_x, self.display_y = 40, 40

        b_w, b_h = self.bounds

        if b_h > 100 and b_w > 100 and b_h - 80 < h:
            im.thumbnail((max(b_w - 320, 320), b_h - 80))
            self.display_w, self.display_h = im.size

        self.scale_factor = self.display_h / self.source_h
        if not keep_rect:
            self.rec_w = round(250 / self.scale_factor)
            self.rec_h = self.rec_w

        if "A" not in im.getbands():
            im.putalpha(int(1 * 256.0))

        by = im.tobytes("raw", "BGRa")
        arr = bytearray(by)

        self.surface = cairo.ImageSurface.create_for_data(
            arr, cairo.FORMAT_ARGB32, self.display_w, self.display_h
        )
        self.ready = True
        self.confine()

    def set_ratio(self):

        if self.crop_ratio and self.crop_ratio != (1, 1):

            if self.crop_ratio == (21, 9) and abs(self.rec_h - 1080) < 50:
                self.rec_h = 1080
                self.rec_w = 2560

            elif self.crop_ratio == (16, 9) and abs(self.rec_h - 1080) < 50:
                self.rec_h = 1080
                self.rec_w = 1920

            else:
                a = self.rec_h // self.crop_ratio[1]
                self.rec_w = a * self.crop_ratio[0]
                self.rec_h = a * self.crop_ratio[1]

    def confine(self):

        if self.lock_ratio:
            self.set_ratio()

        # Confine mask rectangle to self
        if self.rec_x + self.rec_w > self.source_w:
            self.rec_x = self.source_w - self.rec_w
        if self.rec_y + self.rec_h > self.source_h:
            self.rec_y = self.source_h - self.rec_h

        if self.rec_x < 0:
            self.rec_x = 0
        if self.rec_y < 0:
            self.rec_y = 0

        if self.rec_w > self.source_w:
            self.rec_w = self.source_w
            if self.lock_ratio:
                if self.crop_ratio == (1, 1):
                    self.rec_h = self.rec_w

        if self.rec_h > self.source_h:
            self.rec_h = self.source_h
            if self.lock_ratio:
                self.rec_w = self.rec_h

    def load(self, path, bounds):

        self.loaded_fullpath = path
        self.file_name = os.path.splitext(os.path.basename(path))[0]
        self.bounds = bounds
        self.source_image = Image.open(path)

        self.exif = None
        info = self.source_image.info
        if "exif" in info:
            self.exif = piexif.load(info["exif"])

        self.reload()
        self.gen_thumbnails(hq=True)

    def get_display_rect_hw(self):
        return round(self.rec_h + self.rec_w)

    def get_display_rect(self):

        return (round(self.rec_x * self.scale_factor),
                round(self.rec_y * self.scale_factor),
                round(self.rec_w * self.scale_factor),
                round(self.rec_h * self.scale_factor))

    def save_display_rect(self, x, y, w, h):

        self.rec_x = round(x / self.scale_factor)
        self.rec_y = round(y / self.scale_factor)
        self.rec_w = round(w / self.scale_factor)
        self.rec_h = round(h / self.scale_factor)

    def export(self, path=None):

        show_notice = True
        if path is not None:
            show_notice = False
            base_folder = os.path.dirname(path)
        else:
            if self.export_setting == "pictures":
                base_folder = self.pictures_folder
            elif self.export_setting == "download":
                base_folder = self.download_folder
            elif self.export_setting == "overwrite":
                base_folder = os.path.dirname(self.loaded_fullpath)
                path = self.loaded_fullpath
            else:
                print("Export setting error")
                return

        print(f"Target folder is: {base_folder}")

        if not os.path.isdir(base_folder):
            notify_invalid_output.show()

        im = self.source_image
        if not im:
            return

        if self.gray:
            im = im.convert("L")
            im = im.convert("RGB")

        if self.flip_hoz:
            im = im.transpose(method=Image.FLIP_LEFT_RIGHT)
        if self.flip_vert:
            im = im.transpose(method=Image.FLIP_TOP_BOTTOM)

        if self.rotation:
            im = im.rotate(self.rotation, expand=True, resample=Image.BICUBIC)

        cropped = False

        if self.crop:
            cr = im.crop((self.rec_x, self.rec_y, self.rec_x + self.rec_w, self.rec_y + self.rec_h))
            cr.load()
            cropped = True
        else:
            cr = im

        old_size = cr.size
        scaled = False

        if self.export_constrain:
            cr.thumbnail((self.export_constrain, self.export_constrain), Image.ANTIALIAS)

        if old_size != cr.size:
            scaled = True

        cr = self.apply_filters(cr)

        png = self.png

        overwrite = False

        if path is None:

            path = os.path.join(base_folder, self.file_name)

            if cropped:
                path += "-cropped"

            if scaled:
                path += "-scaled"

            ext = '.jpg'
            if png:
                ext = '.png'

        else:
            if path.lower().endswith(".png"):
                png = True
            else:
                png = False
            overwrite = True

        extra = ""

        if not overwrite:
            if os.path.isfile(path + ext):
                i = 0
                while True:
                    i += 1
                    extra = f"({str(i)})"
                    if not os.path.isfile(path + extra + ext):
                        break

            path = path + extra + ext

        if png:
            cr.save(path, "PNG")
        else:

            cr = cr.convert("RGB")

            if self.exif is not None and not self.discard_exif:
                w, h = cr.size
                self.exif["0th"][piexif.ImageIFD.XResolution] = (w, 1)
                self.exif["0th"][piexif.ImageIFD.YResolution] = (h, 1)
                exif_bytes = piexif.dump(self.exif)
                cr.save(path, "JPEG", quality=95, exif=exif_bytes)
            else:

                cr.save(path, "JPEG", quality=95)

        self.last_saved_location = os.path.dirname(path)

        if show_notice:
            notify.show()


picture = Picture()


class SettingsDialog(Gtk.Dialog):

    def toggle_menu_setting_export(self, button, name):
        picture.export_setting = name
        self.avvie.set_export_text()
        config["output-mode"] = name

    def __init__(self, parent, avvie):
        Gtk.Dialog.__init__(self)

        self.set_default_size(170, 120)
        self.set_title("Preferences")
        self.set_transient_for(parent)
        self.avvie = avvie
        box = self.get_content_area()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_spacing(6)
        vbox.set_margin_start(17)
        vbox.set_margin_end(17)
        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)

        l = Gtk.Label()
        l.set_text("Set quick export function")
        vbox.append(l)

        opt = Gtk.CheckButton.new_with_label("Export to Downloads")
        opt.connect("toggled", self.toggle_menu_setting_export, "download")
        vbox.append(opt)
        if picture.export_setting == "download":
            opt.set_active(True)

        opt = Gtk.CheckButton.new_with_label("Export to Pictures")
        opt.connect("toggled", self.toggle_menu_setting_export, "pictures")
        vbox.append(opt)
        if picture.export_setting == "pictures":
            opt.set_active(True)

        opt = Gtk.CheckButton.new_with_label("Overwrite Source File")
        opt.connect("toggled", self.toggle_menu_setting_export, "overwrite")
        vbox.append(opt)
        if picture.export_setting == "overwrite":
            opt.set_active(True)

        vbox.append(Gtk.Separator())

        l = Gtk.Label()
        l.set_text("Add Preview")
        vbox.append(l)

        inline_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        inline_box.set_spacing(7)
        b = Gtk.Button(label="Add")
        b.connect("clicked", avvie.add_preview)
        inline_box.append(b)

        spinbutton = Gtk.SpinButton()
        spinbutton.set_numeric(True)
        spinbutton.set_update_policy(Gtk.SpinButtonUpdatePolicy.ALWAYS)

        spinbutton.set_adjustment(avvie.add_preview_adjustment)

        inline_box.append(spinbutton)

        vbox.append(inline_box)

        box.append(vbox)


class Avvie:
    def __init__(self):
        self.win = None
        self.app = Adw.Application(application_id=app_id)
        self.app.connect('activate', self.on_activate)

        GLib.set_application_name(app_title)

        self.crop_mode_radios = []

    def run(self):
        self.app.run(None)

    def on_activate(self, app):

        sm = app.get_style_manager()
        #sm.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

        self.win = Gtk.ApplicationWindow(application=app)
        self.dw = Gtk.DrawingArea()
        self.about = Gtk.AboutDialog.new()
        self.about.set_transient_for(self.win)

        if not sm.get_dark():
            css = Gtk.CssProvider.new()
            css.load_from_file(Gio.File.new_for_path("pinku.css"))
            Gtk.StyleContext.add_provider_for_display(self.win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)




        self.add_preview_adjustment = Gtk.Adjustment(value=64, lower=16, upper=512, step_increment=16)


        self.save_dialog = Gtk.FileChooserNative.new(title="Choose where to save",
                                            parent=self.win, action=Gtk.FileChooserAction.SAVE)

        f = Gtk.FileFilter()
        f.set_name("Image files")
        f.add_mime_type("image/jpeg")
        f.add_mime_type("image/png")

        self.save_dialog.connect("response", self.save_response)
        self.save_dialog.add_filter(f)

        self.open_dialog = Gtk.FileChooserNative.new(title="Choose an image file",
                                            parent=self.win, action=Gtk.FileChooserAction.OPEN)


        self.open_dialog.add_filter(f)
        self.open_dialog.connect("response", self.open_response)

        self.win.set_title(app_title)
        self.win.set_default_size(1100, 700)

        evk = Gtk.GestureClick.new()
        evk.connect("pressed", self.click)
        evk.connect("released", self.click_up)
        evk.set_button(0)
        self.dw.add_controller(evk)

        evk = Gtk.EventControllerMotion.new()
        evk.connect("motion", self.mouse_motion)
        evk.connect("leave", self.mouse_leave)
        self.dw.add_controller(evk)

        evk = Gtk.EventControllerKey.new()
        evk.connect("key-pressed", self.on_key_press_event)
        evk.connect("key-released", self.on_key_release_event)
        self.win.add_controller(evk)

        # self.connect("key-press-event", self.on_key_press_event)
        # self.connect("key-release-event", self.on_key_release_event)

        dt = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        dt.connect("drop", self.drag_drop_file)
        self.dw.add_controller(dt)

        self.arrow_cursor = Gdk.Cursor.new_from_name("default")

        self.drag_cursor = Gdk.Cursor.new_from_name("move")
        self.br_cursor = Gdk.Cursor.new_from_name("se-resize")
        self.tr_cursor = Gdk.Cursor.new_from_name("ne-resize")
        self.bl_cursor = Gdk.Cursor.new_from_name("sw-resize")
        self.tl_cursor = Gdk.Cursor.new_from_name("nw-resize")


        # Header bar
        hb = Gtk.HeaderBar()
        self.win.set_titlebar(hb)

        # Hb Open file
        button = Gtk.Button()
        button.set_tooltip_text("Open image file")
        button.set_icon_name("document-open-symbolic")
        hb.pack_start(button)
        button.connect("clicked", self.open_file)

        # Hb export image
        button = Gtk.Button()
        button.set_icon_name("document-save-symbolic")
        button.set_sensitive(False)
        button.set_margin_end(10)
        button.connect("clicked", self.save)
        self.quick_export_button = button
        hb.pack_end(button)
        hb.pack_end(Gtk.Separator())

        # hb main menu
        menu = Gtk.MenuButton()
        menu.set_icon_name("open-menu-symbolic")
        menu.set_tooltip_text("Options Menu")
        hb.pack_end(menu)

        # Hb crop switch
        switch = Gtk.Switch()
        switch.connect("notify::active", self.crop_switch)
        switch.set_active(True)
        switch.set_tooltip_text("Enable Crop")
        switch.set_margin_end(10)
        self.crop_switch_button = switch
        image = Gtk.Image.new_from_file("image-crop.svg")
        image.set_margin_end(7)
        box = Gtk.Box()
        box.append(image)
        box.append(switch)
        hb.pack_end(box)

        self.popover = self.gen_main_popover()
        menu.set_popover(self.popover)

        # Thumb menu -----

        menu = Gio.Menu.new()

        action = Gio.SimpleAction.new("toggle-circle", None)
        action.connect("activate", self.click_thumb_menu)
        self.win.add_action(action)
        menu.append("Toggle Circle", "win.toggle-circle")

        action = Gio.SimpleAction.new("remove-thumb", None)
        action.connect("activate", self.click_thumb_menu)
        self.win.add_action(action)
        menu.append("Remove Preview", "win.remove-thumb")

        self.thumb_remove_item = None
        self.thumb_menu = Gtk.PopoverMenu()
        self.thumb_menu.set_menu_model(menu)
        self.thumb_menu.set_parent(self.dw)

        # win drawing area
        self.dw.set_draw_func(self.draw, None)
        self.win.set_child(self.dw)


        # About ---
        self.about.set_authors(["Taiko2k"])
        self.about.set_artists(["Tobias Bernard"])
        self.about.set_copyright("Copyright 2019 Taiko2k captain.gxj@gmail.com")
        self.about.set_license_type(Gtk.License(3))
        self.about.set_website("https://github.com/taiko2k/" + app_title.lower())
        self.about.set_website_label("Github")
        self.about.set_destroy_with_parent(True)
        self.about.set_version(version)
        self.about.set_logo_icon_name(app_id)

        self.win.present()

        self.win.connect("destroy", self.on_exit)

        self.set_export_text()

    def set_export_text(self):
        setting = picture.export_setting
        if setting == "download":
            self.quick_export_button.set_tooltip_text("Export to Downloads folder")
            notify.update(app_title, "Image file exported to Downloads.")
        if setting == "pictures":
            self.quick_export_button.set_tooltip_text("Export to Pictures folder")
            notify.update(app_title, "Image file exported to Pictures.")
        if setting == "overwrite":
            self.quick_export_button.set_tooltip_text("Overwrite Image")
            notify.update(app_title, "Image file overwritten.")

    def open_file(self, button):
        self.open_dialog.show()

    def click(self,  gesture, data, x, y):

        button = gesture.get_current_button()

        if not picture.source_image or not picture.crop:
            return


        # Thumbnails
        w, h = (self.dw.get_width(), self.dw.get_height())
        right = w - 16
        bottom = h - 16
        for i, size in enumerate(picture.thumbs):

            if right - size < x < right and bottom - size < y < bottom:
                if button == 1:
                    picture.circle ^= True

                    self.dw.queue_draw()
                if button == 2:
                    picture.thumbs.remove(size)
                    picture.thumb_surfaces.clear()
                    if not picture.thumbs:
                        picture.thumbs.append(184)
                    picture.gen_thumbnails(hq=True)
                    self.dw.queue_draw()
                    break

                if button == 3:
                    rect = Gdk.Rectangle()
                    rect.x = right - size // 2
                    rect.y = bottom - size
                    rect.w = 0
                    rect.h = 0
                    self.thumb_menu.set_pointing_to(rect)
                    self.thumb_menu.set_position(Gtk.PositionType.TOP)
                    self.thumb_remove_item = size
                    self.thumb_menu.popup()

            right -= 16 + size


        if button == 1:

            rx, ry, rw, rh = picture.get_display_rect()

            if picture.get_display_rect_hw() < picture.all_drag_min and \
                    picture.test_center_start_drag(x, y):
                picture.dragging_center = True

            elif picture.test_tl(x, y):
                picture.dragging_tl = True
            elif picture.test_br(x, y):
                picture.dragging_br = True
            elif picture.test_tr(x, y):
                picture.dragging_tr = True
            elif picture.test_bl(x, y):
                picture.dragging_bl = True

            elif picture.test_center_start_drag(x, y):
                picture.dragging_center = True

            picture.drag_start_position = (x, y)
            picture.original_position = (rx, ry)
            picture.original_drag_size = (rw, rh)

    def click_up(self, gesture, data, x, y):
        button = gesture.get_current_button()

        if button == 1:
            picture.dragging_center = False
            picture.dragging_tl = False
            picture.dragging_br = False
            picture.dragging_bl = False
            picture.dragging_tr = False
            picture.gen_thumbnails(hq=True)

        self.dw.queue_draw()

    def mouse_leave(self, event):
        pass
        #self.win.set_cursor(self.win.arrow_cursor)

    def mouse_motion(self, motion, x, y):

        if not picture.source_image:
            return

        if motion.get_current_event_state() & Gdk.ModifierType.BUTTON1_MASK and picture.crop:

            rx, ry, rw, rh = picture.get_display_rect()

            if picture.drag_start_position is None:
                picture.drag_start_position = (x, y)
                picture.original_position = (rx, ry)
                picture.original_drag_size = (rw, rh)

            offset_x = x - picture.drag_start_position[0]
            offset_y = y - picture.drag_start_position[1]

            dragging_corners = bool(picture.dragging_tl or
                                    picture.dragging_bl or
                                    picture.dragging_br or
                                    picture.dragging_tr)

            if picture.dragging_center and not dragging_corners:

                # Drag mask rectangle relative to original click position
                x_offset = x - picture.drag_start_position[0]
                y_offset = y - picture.drag_start_position[1]

                if picture.slow_drag:
                    x_offset = x_offset // 10
                    y_offset = y_offset // 10

                rx = round(picture.original_position[0] + x_offset)
                ry = round(picture.original_position[1] + y_offset)

            elif not picture.lock_ratio:

                if picture.dragging_tr:

                    ry = round(picture.original_position[1] + offset_y)
                    rh = round(picture.original_drag_size[1] - offset_y)
                    rw = round(picture.original_drag_size[0] + offset_x)

                if picture.dragging_bl:

                    rx = round(picture.original_position[0] + offset_x)
                    rh = round(picture.original_drag_size[1] + offset_y)
                    rw = round(picture.original_drag_size[0] - offset_x)

                elif picture.dragging_tl:

                    rx = round(picture.original_position[0] + offset_x)
                    rw = round(picture.original_drag_size[0] - offset_x)

                    ry = round(picture.original_position[1] + offset_y)
                    rh = round(picture.original_drag_size[1] - offset_y)

                elif picture.dragging_br:

                    rw = round(picture.original_drag_size[0] + offset_x)
                    rh = round(picture.original_drag_size[1] + offset_y)

                if ry < 0:
                    offset = ry * -1
                    ry += offset
                    rh -= offset

                if rx < 0:
                    offset = rx * -1
                    rx += offset
                    rw -= offset

                if rx + rw > picture.display_w:
                    offset = picture.display_w - (rx + rw)
                    offset *= -1
                    rw -= offset

                    if picture.dragging_tr or picture.dragging_br:
                        rx += offset

                if ry + rh > picture.display_h:
                    offset = picture.display_h - (ry + rh)
                    offset *= -1
                    rh -= offset

                    if picture.dragging_tl or picture.dragging_bl:
                        ry += offset

            else:

                if picture.dragging_tr:

                    offset = ((offset_x + (offset_y * -1)) / 2)
                    ry = round(picture.original_position[1] - offset)
                    rh = round(picture.original_drag_size[1] + offset)
                    rw = round(picture.original_drag_size[0] + offset)

                if picture.dragging_bl:

                    offset = (((offset_x * -1) + offset_y) / 2)
                    rx = round(picture.original_position[0] - offset)
                    rh = round(picture.original_drag_size[1] + offset)
                    rw = round(picture.original_drag_size[0] + offset)

                elif picture.dragging_tl:

                    offset = ((offset_x + offset_y) / 2) * -1

                    rx = round(picture.original_position[0] - offset)
                    rw = round(picture.original_drag_size[0] + offset)

                    ry = round(picture.original_position[1] - offset)
                    rh = round(picture.original_drag_size[1] + offset)

                elif picture.dragging_br:

                    offset = (offset_x + offset_y) / 2

                    rw = round(picture.original_drag_size[0] + offset)
                    rh = round(picture.original_drag_size[1] + offset)

                # Don't allow resising past boundary
                if rx + rw > picture.display_w:
                    ratio = rw / rh
                    if picture.dragging_tr:
                        ry += rx + rw - picture.display_w
                    rw = picture.display_w - rx
                    rh = rw * ratio

                if ry + rh > picture.display_h:
                    ratio = rw / rh
                    if picture.dragging_bl:
                        rx += ry + rh - picture.display_h
                    rh = picture.display_h - ry
                    rw = rh * ratio

                if rx < 0:
                    offset = rx * -1
                    ratio = rw / rh
                    rx += offset
                    if picture.dragging_tl:
                        ry += offset
                    rw -= offset
                    rh = rw * ratio

                if ry < 0:
                    offset = ry * -1
                    ratio = rw / rh
                    ry += offset
                    if picture.dragging_tl:
                        rx += offset
                    rh -= offset
                    rw = rh * ratio

                rw = round(rw)
                rh = round(rh)

            if rw < 1:
                rw = 1
            if rh < 1:
                rh = 1

            picture.save_display_rect(rx, ry, rw, rh)

            # picture.corner_hot_area = min(rh * 0.2, 40)

            if picture.dragging_center or dragging_corners:
                self.confine()
                picture.gen_thumbnails()
                self.dw.queue_draw()

        else:
            picture.dragging_center = False


        if picture.crop:

            if picture.get_display_rect_hw() < picture.all_drag_min and \
                    picture.test_center_start_drag(x, y):
                self.dw.set_cursor(self.drag_cursor)

            elif picture.test_br(x, y):
                self.dw.set_cursor(self.br_cursor)
            elif picture.test_tr(x, y):
                self.dw.set_cursor(self.tr_cursor)
            elif picture.test_bl(x, y):
                self.dw.set_cursor(self.bl_cursor)
            elif picture.test_tl(x, y):
                self.dw.set_cursor(self.tl_cursor)
            elif picture.test_center_start_drag(x, y) or picture.dragging_center:
                self.dw.set_cursor(self.drag_cursor)
            else:
                self.dw.set_cursor(self.arrow_cursor)


    def draw(self, area, c, w, h, data):

        background_color = (0.13, 0.13, 0.13)
        c.set_source_rgb(background_color[0], background_color[1], background_color[2])
        c.paint()

        # Draw background grid
        c.set_source_rgb(0.3, 0.3, 0.3)
        c.set_line_width(1)


        size = 8
        for y in range(0, h + 20, 100):
            y += 40
            for x in range(0, w + 20, 100):
                x += 40

                c.move_to(x - size, y)
                c.line_to(x + size, y)
                c.stroke()

                c.move_to(x, y - size)
                c.line_to(x, y + size)
                c.stroke()

        # Draw image
        if picture.ready:

            x = picture.display_x
            y = picture.display_y
            w = picture.display_w
            h = picture.display_h

            # c.save()
            # c.translate(0 + w // 2, 0 + h // 2)
            # c.rotate(math.radians(picture.rotation))
            # c.translate(w // 2 * -1, h // 2 * -1)
            c.set_source_surface(picture.surface, x, y)
            c.paint()
            # c.restore()

            c.set_source_rgba(0, 0, 0, 0.8)

            if picture.crop:
                rx, ry, rw, rh = picture.get_display_rect()

                # Mask out rectangle
                c.rectangle(x, y, rx, h)
                c.fill()
                c.rectangle(x + rx, y, w - rx, ry)
                c.fill()
                c.rectangle(x + rx + rw, y + ry, w - rx - rw, h - ry)
                c.fill()
                c.rectangle(x + rx, y + ry + rh, rw, h - ry - rh)
                c.fill()

                # Draw mask rectangle outline
                c.set_source_rgba(0.6, 0.6, 0.6, 1)
                c.rectangle(x + rx, y + ry, rw, rh)
                c.stroke()

                # Draw mask center lines
                c.set_source_rgba(0.6, 0.6, 0.6, 0.6)
                c.move_to(x + rx + rw // 2, y + ry)
                c.line_to(x + rx + rw // 2, y + ry + rh)
                c.stroke()
                c.move_to(x + rx, y + ry + rh // 2)
                c.line_to(x + rx + rw, y + ry + rh // 2)
                c.stroke()

                c.select_font_face("Sans")
                c.set_font_size(13)
                c.move_to(x + rx, y + ry - 5)

                if picture.rec_h == 1080 and (picture.rec_w == 2560 or picture.rec_w == 1920):
                    c.set_source_rgba(0.2, 0.9, 0.2, 1)
                elif picture.lock_ratio and picture.crop_ratio != (1, 1):
                    if picture.rec_w / picture.crop_ratio[0] * picture.crop_ratio[1] == picture.rec_h:
                        c.set_source_rgba(0.9, 0.9, 0.4, 1)

                c.show_text(f"{picture.rec_w} x {picture.rec_h}")

            w = self.dw.get_width()
            h = self.dw.get_height()

            ex_w = picture.rec_w
            ex_h = picture.rec_h

            if not picture.crop:
                ex_w = picture.source_w
                ex_h = picture.source_h

            ratio = ex_h / ex_w

            if picture.export_constrain:
                if ex_w > picture.export_constrain:
                    ex_w = picture.export_constrain
                    ex_h = int(ex_w * ratio)
                if ex_h > picture.export_constrain:
                    ex_h = picture.export_constrain
                    ex_w = int(ex_w * ratio)

            # if not picture.surface184:
            #     picture.gen_thumb_184(hq=True)


            if picture.thumb_surfaces:
                c.move_to(0, 0)

                right = w - 16
                bottom = h - 16

                for i, size in enumerate(picture.thumbs):
                    if size not in picture.thumb_surfaces:
                        picture.gen_thumbnails(hq=True)


                    if picture.circle:
                        c.save()
                        #c.arc(w - 200 + (184 // 2), h - 200 + (184 // 2), 184 // 2, 0, 2 * math.pi)
                        c.arc(right - size // 2, bottom - size // 2, size // 2, 0, 2 * math.pi)
                        c.clip()
                        #c.set_source_surface(picture.surface184, w - 200, h - 200)
                        c.set_source_surface(picture.thumb_surfaces[size], right - size, bottom - size)
                        c.paint()
                        c.restore()
                    else:
                        #c.set_source_surface(picture.surface184, w - 200, h - 200)
                        c.set_source_surface(picture.thumb_surfaces[size], right - size, bottom - size)
                        c.paint()

                    if i == 0:
                        c.select_font_face("Sans")
                        c.set_font_size(13)
                        c.move_to(right - size, bottom - (size + 5))

                        c.set_source_rgba(0.4, 0.4, 0.4, 1)
                        c.show_text(f"{ex_w} x {ex_h}")

                    if i == 0 and picture.exif and not picture.discard_exif and picture.png is False:
                        c.move_to(right - 32, bottom - (size + 5))

                        c.set_source_rgba(0.4, 0.6, 0.3, 1)
                        c.show_text(f"EXIF")

                    right -= size + 16

    def drag_drop_file(self, drop_target, file, x, y):

        path = file.get_path()

        self.quick_export_button.set_sensitive(True)
        if os.path.isfile(path):
            picture.load(path, (self.dw.get_width(), self.dw.get_height()))
            self.discard_exif_button.set_sensitive(picture.exif and True)

        self.dw.queue_draw()

    def click_thumb_menu(self, action, data):
        name = action.get_name()
        if name == "toggle-circle":
            picture.circle ^= True

        if name == "remove-thumb":
            picture.thumbs.remove(self.thumb_remove_item)
            picture.thumb_surfaces.clear()
            # if not picture.thumbs:
            #     picture.thumbs.append(184)
            picture.gen_thumbnails(hq=True)
        self.dw.queue_draw()

    def on_exit(self, window):

        # Save configuration to json file
        config['thumbs'] = picture.thumbs
        with open(config_file, 'w') as f:
            json.dump(config, f)

    def toggle_menu_setting2(self, button, name):
        picture.lock_ratio = True

        if name == "rect":
            #picture.crop = True
            picture.lock_ratio = False
            #self.preview_circle_check.set_active(False)
            picture.circle = False

        if name == "square":
            #picture.crop = True
            picture.crop_ratio = (1, 1)
            picture.rec_w = picture.rec_h

        if name == '21:9':
            #picture.crop = True
            picture.crop_ratio = (21, 9)
            if picture.source_w >= 2560:
                picture.rec_w = 2560
                picture.rec_h = 1080

            #self.preview_circle_check.set_active(False)

        if name == '16:9':
            #picture.crop = True
            picture.crop_ratio = (16, 9)
            #self.preview_circle_check.set_active(False)

        if name == '16:10':
            #picture.crop = True
            picture.crop_ratio = (16, 10)
            #self.preview_circle_check.set_active(False)

        # if name == 'none':
        #     picture.crop_ratio = (1, 1)
        #     picture.crop = False

        self.confine()
        picture.gen_thumbnails(hq=True)
        self.dw.queue_draw()


    def toggle_flip_vert(self, button):
        picture.flip_vert ^= True
        if picture.source_image:
            picture.reload(keep_rect=True)
            self.dw.queue_draw()
            picture.gen_thumbnails(hq=True)

    def toggle_flip_hoz(self, button):
        picture.flip_hoz ^= True
        if picture.source_image:
            picture.reload(keep_rect=True)
            self.dw.queue_draw()
            picture.gen_thumbnails(hq=True)

    def rotate_reset(self, button):

        picture.rotation = 0
        self.rot.set_value(0)
        if picture.source_image:
            picture.reload(keep_rect=True)
            self.dw.queue_draw()
            picture.gen_thumbnails(hq=True)
        self.rotate_reset_button.set_sensitive(False)

    def rotate(self, scale):

        picture.rotation = scale.get_value() * -1
        self.rotate_reset_button.set_sensitive(True)
        if picture.source_image:
            picture.reload(keep_rect=True)
            self.dw.queue_draw()
            #picture.gen_thumb_184(hq=True)

    def toggle_menu_setting(self, button, name):

        if name == 'circle':
            picture.circle ^= True
            self.dw.queue_draw()

        if name == 'grayscale':
            picture.gray ^= True
            self.dw.queue_draw()

        if name == 'sharpen':
            picture.sharpen = button.get_active()

        if name == "png":
            picture.png = button.get_active()

        if name == "exif":
            picture.discard_exif = button.get_active()

        if name == "1:1" and button.get_active():
            picture.export_constrain = None

        if name == "184" and button.get_active():
            picture.export_constrain = 184

        if name == "500" and button.get_active():
            picture.export_constrain = 500

        if name == "750" and button.get_active():
            picture.export_constrain = 750

        if name == "1000" and button.get_active():
            picture.export_constrain = 1000

        if name == "1920" and button.get_active():
            picture.export_constrain = 1920

        if name == "custom" and button.get_active():
            picture.export_constrain = int(self.custom_resize_adjustment.get_value())

        picture.gen_thumbnails(hq=True)
        self.dw.queue_draw()

    def save(self, widget):
        picture.export()

    def set_custom_resize(self, adjustment):
        if self.custom_resize_radio.get_active():
            picture.export_constrain = int(adjustment.get_value())

    def gen_main_popover(self):

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_spacing(5)
        vbox.set_margin_start(15)
        vbox.set_margin_end(15)
        vbox.set_margin_top(15)
        vbox.set_margin_bottom(15)

        opt = Gtk.CheckButton.new_with_label("Square")
        opt.connect("toggled", self.toggle_menu_setting2, "square")
        opt.set_active(True)
        vbox.append(opt)
        opt2 = opt

        opt = Gtk.CheckButton.new_with_label("Free Rectangle")
        self.free_rectangle_radio = opt
        self.crop_mode_radios.append(opt)
        opt.connect("toggled", self.toggle_menu_setting2, "rect")
        opt.set_group(opt2)
        vbox.append(opt)

        opt = Gtk.CheckButton.new_with_label("16:10")
        opt.set_group(opt2)
        self.crop_mode_radios.append(opt)
        opt.connect("toggled", self.toggle_menu_setting2, "16:10")
        vbox.append(opt)

        opt = Gtk.CheckButton.new_with_label("16:9")
        opt.set_group(opt2)
        self.crop_mode_radios.append(opt)
        opt.connect("toggled", self.toggle_menu_setting2, "16:9")
        vbox.append(opt)

        opt = Gtk.CheckButton.new_with_label("21:9")
        opt.set_group(opt2)
        self.crop_mode_radios.append(opt)
        opt.connect("toggled", self.toggle_menu_setting2, "21:9")
        vbox.append(opt)

        self.rotate_reset_button = Gtk.Button(label="Reset rotation")
        self.rot = Gtk.Scale.new_with_range(orientation=0, min=-90, max=90, step=2)
        self.rotate_reset_button.connect("clicked", self.rotate_reset)
        self.rotate_reset_button.set_sensitive(False)
        self.rot.set_value(0)
        self.rot.set_size_request(180, -1)
        self.rot.set_draw_value(False)
        self.rot.set_has_origin(False)
        self.rot.connect("value-changed", self.rotate)
        vbox.append(self.rot)
        vbox.append(self.rotate_reset_button)

        flip_vert_button = Gtk.Button(label="Flip Vertical")
        flip_vert_button.connect("clicked", self.toggle_flip_vert)
        vbox.append(flip_vert_button)
        flip_hoz_button = Gtk.Button(label="Flip Horizontal")
        flip_hoz_button.connect("clicked", self.toggle_flip_hoz)
        vbox.append(flip_hoz_button)



        vbox2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox2.set_spacing(5)
        vbox2.set_margin_start(15)
        vbox2.set_margin_end(15)
        vbox2.set_margin_top(15)
        vbox2.set_margin_bottom(15)

        opt = Gtk.CheckButton.new_with_label("No Downscale")
        opt.connect("toggled", self.toggle_menu_setting, "1:1")
        vbox2.append(opt)
        opt2 = opt

        opt = Gtk.CheckButton.new_with_label("Max 184x184")
        opt.connect("toggled", self.toggle_menu_setting, "184")
        opt.set_group(opt2)
        vbox2.append(opt)

        opt = Gtk.CheckButton.new_with_label("Max 1000x1000")
        opt.connect("toggled", self.toggle_menu_setting, "1000")
        opt.set_group(opt2)
        vbox2.append(opt)

        inline_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.custom_resize_radio = Gtk.CheckButton.new_with_label("Custom")
        self.custom_resize_radio.connect("toggled", self.toggle_menu_setting, "custom")
        self.custom_resize_radio.set_group(opt2)
        inline_box.append(self.custom_resize_radio)

        self.custom_resize_adjustment = Gtk.Adjustment(value=1920, lower=2, upper=10000, step_increment=50)
        self.custom_resize_adjustment.connect("value-changed", self.set_custom_resize)

        spinbutton = Gtk.SpinButton()
        spinbutton.set_numeric(True)
        spinbutton.set_update_policy(Gtk.SpinButtonUpdatePolicy.ALWAYS)
        spinbutton.set_adjustment(self.custom_resize_adjustment)
        inline_box.append(spinbutton)

        vbox2.append(inline_box)

        vbox2.append(Gtk.Separator())

        pn = Gtk.CheckButton()
        pn.set_label("Export as PNG")
        pn.connect("toggled", self.toggle_menu_setting, "png")
        vbox2.append(pn)

        pn = Gtk.CheckButton()
        pn.set_label("Discard EXIF")
        pn.set_sensitive(False)
        pn.connect("toggled", self.toggle_menu_setting, "exif")
        self.discard_exif_button = pn
        vbox2.append(pn)

        sh = Gtk.CheckButton()
        sh.set_label("Sharpen")
        sh.connect("toggled", self.toggle_menu_setting, "sharpen")
        vbox2.append(sh)

        sh = Gtk.CheckButton()
        sh.set_label("Grayscale")
        sh.connect("toggled", self.toggle_menu_setting, "grayscale")
        vbox2.append(sh)

        vbox2.append(Gtk.Separator())

        m1 = Gtk.Button(label="Export As")
        m1.connect("clicked", self.export_as)
        vbox2.append(m1)

        m1 = Gtk.Button(label="Preferences")
        m1.connect("clicked", self.open_pref)
        vbox2.append(m1)


        m1 = Gtk.Button(label="About " + app_title)
        m1.connect("clicked", self.show_about)
        vbox2.append(m1)



        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.append(vbox)
        hbox.append(Gtk.Separator())
        hbox.append(vbox2)

        popover = Gtk.Popover()

        popover.set_child(hbox)

        return popover

    def confine(self):
        picture.confine()

    def crop_switch(self, switch, param):

        if switch.get_active():
            picture.crop = True
        else:
            picture.crop = False

        for button in self.crop_mode_radios:
            button.set_sensitive(picture.crop)

        self.confine()
        picture.gen_thumbnails(hq=True)
        self.dw.queue_draw()

    def on_key_press_event(self, event, keyval, keycode, state):

        if keyval == Gdk.KEY_Shift_L or keyval == Gdk.KEY_Shift_R:
            picture.slow_drag = True
            picture.drag_start_position = None

        if keyval == Gdk.KEY_Control_L and not self.free_rectangle_radio.get_active():
            self.free_rectangle_radio.set_active(True)

        if keyval == Gdk.KEY_Right:
            picture.rec_x += 1
            picture.gen_thumbnails(hq=True)
            self.dw.queue_draw()

        if keyval == Gdk.KEY_Left:
            picture.rec_x -= 1
            picture.gen_thumbnails(hq=True)
            self.dw.queue_draw()

        if keyval == Gdk.KEY_Up:
            picture.rec_y -= 1
            picture.gen_thumbnails(hq=True)
            self.dw.queue_draw()

        if keyval == Gdk.KEY_Down:
            picture.rec_y += 1
            picture.gen_thumbnails(hq=True)
            self.dw.queue_draw()


    def on_key_release_event(self,  event, keyval, keycode, state):

        if keyval == Gdk.KEY_Shift_L or keyval == Gdk.KEY_Shift_R:
            picture.slow_drag = False
            picture.drag_start_position = None

    def open_response(self, dialog, response):

        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            filename = file.get_path()
            print("File selected: " + filename)
            self.quick_export_button.set_sensitive(True)
            picture.load(filename, (self.dw.get_width(), self.dw.get_height()))
            self.dw.queue_draw()
            self.discard_exif_button.set_sensitive(picture.exif and True)

    def show_about(self, button):
        self.about.present()
        self.popover.hide()
        #self.about.hide()
        # self.about.run()
        # self.about.hide()

    def open_pref(self, button):

        dialog = SettingsDialog(self.win, self)
        dialog.show()
        self.popover.hide()

    def add_preview(self, button):

        size = int(self.add_preview_adjustment.get_value())
        if size not in picture.thumbs:
            picture.thumbs.append(size)
            picture.thumbs.sort(reverse=True)
            picture.thumb_surfaces.clear()
            picture.gen_thumbnails(hq=True)
            self.dw.queue_draw()

    def export_as(self, button):

        if not picture.ready:
            return

        self.save_dialog.show()
        self.popover.hide()

    def save_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            filename = file.get_path()
            picture.export(filename)

# Create a new application
avvie = Avvie()
avvie.run()

