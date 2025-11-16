import os
import threading
from tkinter import (
    Tk, Frame, Label, Button, Canvas,
    StringVar, BooleanVar, filedialog
)
from tkinter import ttk

import numpy as np
from PIL import Image
from PyInstaller.utils.hooks import collect_dynamic_libs
from moviepy.editor import VideoFileClip, ImageSequenceClip

numpy_binaries = collect_dynamic_libs("numpy")
import imageio
import imageio_ffmpeg

# ============================================================
# PALETTES
# ============================================================

PALETTES = {
    "CGA Mode #1": {
        "colors": ["#FF00FF", "#00FFFF", "#FFFFFF", "#000000"],
        "native": (320, 200),
        "type": "explicit"
    },
    "CGA Mode #2": {
        "colors": ["#FF0000", "#FFFF00", "#00FF00", "#000000"],
        "native": (320, 200),
        "type": "explicit"
    },
    "EGA Mode #2": {
        "colors": [
            "#FF00FF", "#00FFFF", "#FFFFFF", "#FF0000",
            "#FFFF00", "#00FF00", "#0000FF", "#555555",
            "#AAAAAA", "#AA00AA", "#00AAAA", "#AA0000",
            "#AA5500", "#00AA00", "#0000AA"
        ],
        "native": (320, 200),
        "type": "explicit"
    },
    "Commodore 64": {
        "colors": [
            "#FFFFFF", "#000000", "#A14D43", "#6AC1C8",
            "#A257A5", "#5CAD5F", "#4F449C", "#CBD689",
            "#A3683A", "#6E540B", "#CC7F76", "#636363",
            "#8B8B8B", "#8A7FCD", "#AFAFAF"
        ],
        "native": (320, 200),
        "type": "explicit"
    },
    "NES": {
        "colors": [
            "#7C7C7C", "#0000FC", "#0000BC", "#4428BC",
            "#940084", "#A80020", "#A81000", "#881400",
            "#503000", "#007800", "#006800", "#005800",
            "#004058", "#000000", "#BCBCBC", "#0078F8",
            "#0058F8", "#6844FC", "#D800CC", "#E40058",
            "#F83800", "#E45C10", "#AC7C00", "#00B800",
            "#00A800", "#00A844", "#008888", "#F8F8F8",
            "#3CBCFC", "#6888FC", "#9878F8", "#F878F8",
            "#F85898", "#F87858", "#FCA044", "#F8B800",
            "#B8F818", "#58D854", "#58F898", "#00E8D8",
            "#787878", "#FCFCFC", "#A4E4FC", "#B8B8F8",
            "#D8B8F8", "#F8B8F8", "#F8A4C0", "#F0D0B0",
            "#FCE0A8", "#F8D878", "#D8F878", "#B8F8B8",
            "#B8F8D8", "#00FCFC", "#F8D8F8"
        ],
        "native": (256, 224),
        "type": "explicit"
    },
    "Sega Master System (6-bit RGB)": {
        "colors": None,
        "native": (256, 192),
        "type": "bitdepth",
        "levels": 4  # 2 bits per channel
    },
    "Sega Genesis (9-bit RGB)": {
        "colors": None,
        "native": (320, 224),
        "type": "bitdepth",
        "levels": 8  # 3 bits per channel
    }
}

# ============================================================
# DARK THEME COLORS
# ============================================================

BG = "#1e1e1e"
PANEL = "#252526"
BORDER = "#3c3c3c"
TEXT = "#cccccc"
BTN_BG = "#3a3a3a"
BTN_FG = "#ffffff"

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def build_palette_image(colors):
    pal_img = Image.new("P", (16, 16))
    pal = []
    for c in colors:
        pal.extend(hex_to_rgb(c))
    pal.extend([0] * (768 - len(pal)))
    pal_img.putpalette(pal)
    return pal_img

# --- Ordered Bayer 8×8 matrix --------------------------------

BAYER_8x8 = [
     0,48,12,60, 3,51,15,63,
    32,16,44,28,35,19,47,31,
     8,56, 4,52,11,59, 7,55,
    40,24,36,20,43,27,39,23,
     2,50,14,62, 1,49,13,61,
    34,18,46,30,33,17,45,29,
    10,58, 6,54, 9,57, 5,53,
    42,26,38,22,41,25,37,21
]

def ordered_dither(img, palette_img):
    w, h = img.size
    img = img.convert("RGB")
    base = img.load()

    for y in range(h):
        for x in range(w):
            r, g, b = base[x, y]
            threshold = BAYER_8x8[(y % 8) * 8 + (x % 8)]
            threshold = (threshold / 64.0) * 255
            r = 255 if r > threshold else 0
            g = 255 if g > threshold else 0
            b = 255 if b > threshold else 0
            base[x, y] = (r, g, b)

    q = img.quantize(palette=palette_img, dither=Image.NONE)
    return q.convert("RGB")

def apply_palette(img, palette_name, dither):
    pinfo = PALETTES[palette_name]

    # BITDEPTH SYSTEM (Master System / Genesis)
    if pinfo["type"] == "bitdepth":
        levels = pinfo["levels"]
        img = img.convert("RGB")
        px = img.load()
        w, h = img.size
        for y in range(h):
            for x in range(w):
                r, g, b = px[x, y]
                r = round((r / 255) * (levels - 1)) * (255 // (levels - 1))
                g = round((g / 255) * (levels - 1)) * (255 // (levels - 1))
                b = round((b / 255) * (levels - 1)) * (255 // (levels - 1))
                px[x, y] = (r, g, b)
        return img

    # EXPLICIT PALETTE
    colors = pinfo["colors"]
    pal_img = build_palette_image(colors)

    if dither == "None":
        q = img.convert("RGB").quantize(palette=pal_img, dither=Image.NONE)
        return q.convert("RGB")

    if dither == "Bayer Ordered (8×8)":
        return ordered_dither(img, pal_img)

    return img

# --- Letterbox scaling ---------------------------------------

def letterbox_to_native(img, system_name):
    native_w, native_h = PALETTES[system_name]["native"]
    src_w, src_h = img.size
    target_ratio = native_w / native_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_w = native_w
        new_h = int(native_w / src_ratio)
    else:
        new_h = native_h
        new_w = int(native_h * src_ratio)

    resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
    canvas = Image.new("RGB", (native_w, native_h), (0, 0, 0))
    offset = ((native_w - new_w) // 2, (native_h - new_h) // 2)
    canvas.paste(resized, offset)
    return canvas

def is_image_file(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in (".png", ".jpg", ".jpeg", ".bmp")

def is_video_file(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in (".mp4", ".mov", ".avi", ".mkv")

# ============================================================
# UI CLASS
# ============================================================

class MM2RApp:
    def __init__(self, root):
        self.root = root
        root.title("MM2R — ModernMedia2Retro")
        root.configure(bg=BG)
        root.geometry("900x500")

        self.input_path = StringVar()
        self.output_dir = StringVar()
        self.palette_choice = StringVar(value="CGA Mode #1")
        self.dither_choice = StringVar(value="None")
        self.force_native = BooleanVar(value=False)
        self.debug_log = BooleanVar(value=False)
        self.status = StringVar()
        self.progress_pct = StringVar(value="")

        self.build_ui()

    # ---------------------------------------------------------
    def build_ui(self):
        # LEFT PANEL
        left = Frame(self.root, bg=PANEL, bd=1, relief="solid")
        left.place(x=0, y=0, width=300, height=500)

        Label(left, text="PALETTE", bg=PANEL, fg=TEXT,
              font=("Segoe UI", 11, "bold")).pack(pady=10)
        ttk.OptionMenu(left, self.palette_choice, self.palette_choice.get(),
                       *PALETTES.keys(),
                       command=lambda _: self.update_palette_preview()).pack()

        # Palette preview
        Label(left, text="Palette Preview", bg=PANEL, fg=TEXT).pack(pady=10)
        self.preview = Canvas(left, width=260, height=130, bg=BG,
                              highlightthickness=1, highlightbackground=BORDER)
        self.preview.pack(pady=5)
        self.update_palette_preview()

        # Dithering
        Label(left, text="Dithering", bg=PANEL, fg=TEXT,
              font=("Segoe UI", 10, "bold")).pack(pady=10)
        ttk.OptionMenu(left, self.dither_choice, self.dither_choice.get(),
                       "None", "Bayer Ordered (8×8)").pack()

        # Checkboxes
        ttk.Checkbutton(left, text="Convert to native resolution",
                        variable=self.force_native).pack(pady=10)
        ttk.Checkbutton(left, text="Create debug log (images only)",
                        variable=self.debug_log).pack()

        # RIGHT PANEL
        right = Frame(self.root, bg=BG)
        right.place(x=300, y=0, width=600, height=500)

        Label(right, text="Input (Image or Video)", bg=BG, fg=TEXT,
              font=("Segoe UI", 10, "bold")).pack(pady=5)
        Button(right, text="Select File", bg=BTN_BG, fg=BTN_FG,
               command=self.select_input).pack()
        Label(right, textvariable=self.input_path, bg=BG, fg=TEXT,
              wraplength=550).pack(pady=5)

        Label(right, text="Output Folder", bg=BG, fg=TEXT,
              font=("Segoe UI", 10, "bold")).pack(pady=5)
        Button(right, text="Select Folder", bg=BTN_BG, fg=BTN_FG,
               command=self.select_output).pack()
        Label(right, textvariable=self.output_dir, bg=BG, fg=TEXT,
              wraplength=550).pack(pady=5)

        # Status
        self.status_label = Label(
            right, textvariable=self.status,
            bg=BG, fg="#ff6666",
            wraplength=550, font=("Segoe UI", 10)
        )
        self.status_label.pack(pady=10)

        # Progress bar
        self.progress = ttk.Progressbar(right, length=400, mode="determinate")
        self.progress.pack(pady=10)

        # Percentage label
        self.progress_label = Label(
            right,
            textvariable=self.progress_pct,
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 9)
        )
        self.progress_label.pack(pady=(0, 10))

        # Convert button
        Button(right, text="START CONVERSION!", bg="#4caf50", fg="white",
               font=("Segoe UI", 12, "bold"), width=20,
               command=self.start_conversion).pack(pady=20)

        # Footer
        Label(right, text="Created by Jonathan Lipman for HackRPI 2025\nNovember 16th, 2025 5:48AM Build",
              bg=BG, fg="#888888", font=("Segoe UI", 9)).pack(side="bottom", pady=10)

    # ---------------------------------------------------------
    def update_palette_preview(self):
        self.preview.delete("all")
        info = PALETTES[self.palette_choice.get()]

        if info["type"] == "explicit":
            colors = info["colors"]
            cols = 8
            size = 20
            for i, c in enumerate(colors):
                x = (i % cols) * size
                y = (i // cols) * size
                self.preview.create_rectangle(x, y, x + size, y + size,
                                              fill=c, width=0)
        else:
            self.preview.create_text(
                130, 65,
                text="Bitdepth palette\n(auto-generated)",
                fill=TEXT, font=("Segoe UI", 10)
            )

    # ---------------------------------------------------------
    def select_input(self):
        path = filedialog.askopenfilename(
            filetypes=[("Media", "*.png;*.jpg;*.jpeg;*.bmp;*.mp4;*.mov;*.avi;*.mkv")]
        )
        if path:
            self.input_path.set(path)

    def select_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_dir.set(path)

    # ---------------------------------------------------------
    def update_video_progress(self, fraction: float):
        """Update progress bar and percentage text from 0.0–1.0."""
        pct = max(0.0, min(1.0, fraction)) * 100.0
        self.progress["value"] = pct
        self.progress_pct.set(f"{pct:5.1f}%")

    # ---------------------------------------------------------
    def start_conversion(self):
        self.status.set("")
        self.progress["value"] = 0
        self.progress_pct.set("")

        inp = self.input_path.get()
        outdir = self.output_dir.get()
        palette = self.palette_choice.get()
        dither = self.dither_choice.get()
        force_native = self.force_native.get()
        debug_log = self.debug_log.get()

        if not inp or not os.path.isfile(inp):
            self.status_label.config(fg="#ff6666")
            self.status.set("❗ Please select a valid input file.")
            return
        if not outdir or not os.path.isdir(outdir):
            self.status_label.config(fg="#ff6666")
            self.status.set("❗ Please select a valid output folder.")
            return

        is_img = is_image_file(inp)
        is_vid = is_video_file(inp)

        if not (is_img or is_vid):
            self.status_label.config(fg="#ff6666")
            self.status.set("❗ Unsupported file type. Use PNG/JPEG/BMP or MP4/MOV/AVI/MKV.")
            return

        if is_vid and debug_log:
            self.status_label.config(fg="#ff6666")
            self.status.set("❗ Debug log option is for images only. Disable it for video.")
            return

        base = os.path.splitext(os.path.basename(inp))[0]
        if is_img:
            out_ext = ".png"   # always PNG for images
        else:
            out_ext = ".mp4"   # re-encode to MP4 for video

        final_path = os.path.join(outdir, f"{base}_{palette.replace(' ', '_')}{out_ext}")

        # UI state before starting
        self.status_label.config(fg="#cccccc")
        self.status.set("Converting... Please wait warmly.")
        self.progress["value"] = 0
        self.progress_pct.set("0.0%")

        def worker():
            try:
                if is_img:
                    # IMAGE PATH
                    img = Image.open(inp)
                    if force_native:
                        img = letterbox_to_native(img, palette)
                    img = apply_palette(img, palette, dither)
                    img.save(final_path)

                    # Debug log
                    if debug_log:
                        with open(final_path + ".log.txt", "w") as f:
                            f.write("ModernMedia2Retro Conversion Log\n")
                            f.write(f"Input: {inp}\n")
                            f.write(f"Output: {final_path}\n")
                            f.write(f"Palette: {palette}\n")
                            f.write(f"Native Resolution Mode: {force_native}\n")
                            f.write(f"Dithering: {dither}\n")

                    def on_success_img():
                        self.progress["value"] = 100
                        self.progress_pct.set("100.0%")
                        self.status_label.config(fg="#66ff66")
                        self.status.set(f"File Completed and saved as: {final_path}")

                    self.root.after(0, on_success_img)

                else:
                    # VIDEO PATH with frame-by-frame progress
                    clip = VideoFileClip(inp)
                    fps = clip.fps
                    duration = clip.duration
                    total_frames = max(1, int(fps * duration))

                    frames = []

                    def process_frame_array(frame_array):
                        """Apply palette pipeline to a single frame (numpy array)."""
                        img = Image.fromarray(frame_array)
                        if force_native:
                            img = letterbox_to_native(img, palette)
                        img = apply_palette(img, palette, dither)
                        return np.array(img.convert("RGB"))

                    for idx, frame in enumerate(clip.iter_frames()):
                        processed = process_frame_array(frame)
                        frames.append(processed)

                        fraction = (idx + 1) / total_frames

                        def _update(f=fraction):
                            self.update_video_progress(f)
                        self.root.after(0, _update)

                    new_clip = ImageSequenceClip(frames, fps=fps)
                    # Preserve original audio if present
                    if clip.audio is not None:
                        new_clip = new_clip.set_audio(clip.audio)

                    new_clip.write_videofile(final_path, audio=True)
                    clip.close()
                    new_clip.close()

                    def on_success_vid():
                        self.progress["value"] = 100
                        self.progress_pct.set("100.0%")
                        self.status_label.config(fg="#66ff66")
                        self.status.set(f"File completed and saved as: {final_path}")

                    self.root.after(0, on_success_vid)

            except Exception as e:
                def on_error():
                    self.progress["value"] = 0
                    self.progress_pct.set("")
                    self.status_label.config(fg="#ff6666")
                    self.status.set(f"❗ Error: {e}")
                self.root.after(0, on_error)

        threading.Thread(target=worker, daemon=True).start()

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    root = Tk()
    app = MM2RApp(root)
    root.mainloop()