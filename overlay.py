#!/usr/bin/env python3
"""Wayland layer-shell overlay hosting the Palworld live map.

A layer-shell surface on the OVERLAY layer draws above fullscreen windows,
which a normal keep-above window cannot do under KWin.

The page moves and resizes the window by posting messages to the "overlay"
script handler - layer surfaces have no titlebar and cannot be dragged by the
compositor, so Alt+right-drag is translated into margin changes here.
"""
import argparse, json, os, sys

# GDK picks its backend when GTK initialises on import, so this must come first.
os.environ.setdefault("GDK_BACKEND", "wayland")
# KWin + GTK3/Mesa hit "explicit sync is used, but no acquire point is set" on the
# accelerated path; CPU compositing dodges it and keeps the GPU free for the game.
os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, WebKit2, GtkLayerShell  # noqa: E402

EDGES = {
    "top-left":     (True,  False, True,  False),
    "top-right":    (True,  False, False, True),
    "bottom-left":  (False, True,  True,  False),
    "bottom-right": (False, True,  False, True),
}
STATE = os.path.expanduser("~/.local/share/palworld-live-map/window.json")


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(d):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w") as f:
            json.dump(d, f)
    except Exception:
        pass


class Overlay:
    def __init__(self, args):
        self.args = args
        st = load_state()
        self.w = int(st.get("width", args.width))
        self.h = int(st.get("height", args.height))
        self.anchor = st.get("anchor", args.anchor)
        # margins from the two anchored edges
        self.mx = int(st.get("mx", args.margin))   # left or right
        self.my = int(st.get("my", args.margin))   # top or bottom

        self.win = Gtk.Window()
        self.win.set_default_size(self.w, self.h)
        self.win.set_size_request(self.w, self.h)

        GtkLayerShell.init_for_window(self.win)
        GtkLayerShell.set_namespace(self.win, "palworld-overlay")
        GtkLayerShell.set_layer(
            self.win,
            GtkLayerShell.Layer.OVERLAY if args.layer == "overlay"
            else GtkLayerShell.Layer.TOP,
        )
        GtkLayerShell.set_keyboard_mode(
            self.win,
            GtkLayerShell.KeyboardMode.NONE if args.click_through
            else GtkLayerShell.KeyboardMode.ON_DEMAND,
        )
        self._apply_anchor()

        ucm = WebKit2.UserContentManager()
        ucm.register_script_message_handler("overlay")
        ucm.connect("script-message-received::overlay", self.on_message)

        self.view = WebKit2.WebView.new_with_user_content_manager(ucm)
        s = self.view.get_settings()
        s.set_property("enable-developer-extras", True)
        s.set_property("enable-write-console-messages-to-stdout", True)
        self.view.connect("load-changed",
                          lambda _v, e: print(f"load: {e.value_nick}", flush=True))
        self.view.connect("load-failed", self.on_fail)
        self.view.load_uri(args.url)

        self.win.add(self.view)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.show_all()

        if args.click_through:
            import cairo
            gw = self.win.get_window()
            if gw is not None:
                gw.input_shape_combine_region(cairo.Region(), 0, 0)

    def on_fail(self, _v, _e, uri, err):
        print(f"LOAD FAILED {uri}: {err.message}", file=sys.stderr, flush=True)
        return False

    def _apply_anchor(self):
        top, bottom, left, right = EDGES[self.anchor]
        for edge, on, m in (
            (GtkLayerShell.Edge.TOP, top, self.my),
            (GtkLayerShell.Edge.BOTTOM, bottom, self.my),
            (GtkLayerShell.Edge.LEFT, left, self.mx),
            (GtkLayerShell.Edge.RIGHT, right, self.mx),
        ):
            GtkLayerShell.set_anchor(self.win, edge, on)
            if on:
                GtkLayerShell.set_margin(self.win, edge, m)

    def _persist(self):
        save_state({"width": self.w, "height": self.h, "anchor": self.anchor,
                    "mx": self.mx, "my": self.my})

    def on_message(self, _ucm, result):
        try:
            raw = result.get_js_value().to_string()
            msg = json.loads(raw)
        except Exception as e:
            print("bad overlay message:", e, file=sys.stderr, flush=True)
            return

        act = msg.get("action")
        if act == "drag":
            top, bottom, left, right = EDGES[self.anchor]
            dx, dy = int(msg.get("dx", 0)), int(msg.get("dy", 0))
            # moving right must shrink a right margin, and likewise for bottom
            self.mx += dx if left else -dx
            self.my += dy if top else -dy
            mon = self.win.get_display().get_monitor_at_window(self.win.get_window())
            geo = mon.get_geometry() if mon else None
            if geo:
                self.mx = max(0, min(self.mx, max(0, geo.width - self.w)))
                self.my = max(0, min(self.my, max(0, geo.height - self.h)))
            else:
                self.mx = max(0, self.mx)
                self.my = max(0, self.my)
            self._apply_anchor()
        elif act == "dragEnd":
            self._persist()
        elif act == "resize":
            self.w = max(280, min(int(msg.get("w", self.w)), 3000))
            self.h = max(240, min(int(msg.get("h", self.h)), 2000))
            self.win.set_size_request(self.w, self.h)
            self.win.resize(self.w, self.h)
            self._persist()
        elif act == "anchor":
            a = msg.get("anchor")
            if a in EDGES:
                self.anchor = a
                self._apply_anchor()
                self._persist()
        elif act == "quit":
            Gtk.main_quit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=700)
    ap.add_argument("--anchor", default="top-right", choices=list(EDGES))
    ap.add_argument("--margin", type=int, default=16)
    ap.add_argument("--layer", default="overlay", choices=["overlay", "top"])
    ap.add_argument("--click-through", action="store_true",
                    help="pointer events pass straight to the game")
    args = ap.parse_args()

    if not GtkLayerShell.is_supported():
        sys.exit("layer-shell not supported (need a native Wayland session)")

    Overlay(args)
    Gtk.main()


if __name__ == "__main__":
    main()
