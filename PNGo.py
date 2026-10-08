#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PNGo — drag & drop конвертер PSD / PSB и растровых изображений в PNG.

Перетащи файл в окно программы — рядом появится PNG с прозрачностью.
Поддерживает PSD, PSB, TIFF, JPG, GIF, WEBP, BMP, TGA, ICO и др.

Репозиторий: https://github.com/NikiFils/PNGo
Лицензия:    MIT
"""

import json
import os
import threading
import tkinter as tk
from tkinter import ttk, colorchooser
from tkinterdnd2 import DND_FILES, TkinterDnD
from pathlib import Path
from PIL import Image, ImageSequence

# ---------------- Метаданные ----------------
APP_NAME = "PNGo"
APP_VERSION = "1.0"
APP_AUTHOR = "NikiFils"
APP_YEAR = "2026"

# ---------------- Форматы ----------------
PSD_EXT = {'.psd', '.psb'}
IMG_EXT = {'.tif', '.tiff', '.jpg', '.jpeg', '.jfif', '.png', '.bmp',
           '.gif', '.webp', '.tga', '.ico', '.ppm', '.pgm', '.pbm',
           '.pcx', '.dds', '.eps'}

# ---------------- Настройки ----------------
SETTINGS_PATH = Path(os.getenv("APPDATA", Path.home())) / "pngo.json"

DEFAULT_SETTINGS = {
    "tooltips": True,
    "transparency": True,
    "bg_color": "#ffffff",
    "compression": 6,
    "resize_max": 0,
    "trim": False,
    "overwrite_mode": "overwrite",   # overwrite | skip | suffix
    "suffix": "",
    "topmost": False,
    "remember_geometry": True,
    "geometry": "",
}
settings = dict(DEFAULT_SETTINGS)


def load_settings():
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text("utf-8"))
            for k in DEFAULT_SETTINGS:
                if k in data:
                    settings[k] = data[k]
    except Exception:
        pass


def save_settings():
    try:
        SETTINGS_PATH.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


# ---------------- Тексты ----------------
HELP_TEXT = f"""КАК ПОЛЬЗОВАТЬСЯ

1. Перетащи мышкой PSD, PSB или любой растровый файл
   прямо в окно программы. Можно сразу несколько.

2. Рядом с исходным файлом появится PNG.

3. Что делать, если PNG уже есть — настраивается
   во вкладке «Файлы» окна настроек:
   перезапись / пропуск / автонумерация.

ПОДДЕРЖИВАЕМЫЕ ФОРМАТЫ

  • Adobe Photoshop:  .psd, .psb
  • Растровые:        .tif/.tiff, .jpg/.jpeg/.jfif,
                      .png, .bmp, .gif, .webp, .tga,
                      .ico, .ppm/.pgm/.pbm, .pcx, .dds, .eps

НАСТРОЙКИ (кнопка «Настройки»)

  Изображение
   • Прозрачность — оставить альфу или залить фоном
     (цвет фона выбирается).
   • Сжатие PNG — 0 (быстро, большой файл) …
     9 (медленно, маленький файл).
   • Уменьшить до — ресайз по длинной стороне, 0 = не менять.
   • Обрезать пустые края — отрезать прозрачные поля
     вокруг содержимого.

  Файлы
   • Если PNG существует: перезапись / пропуск / _1, _2 …
   • Суффикс к имени — например photo.png → photo_out.png.

  Интерфейс
   • Всплывающие подсказки при наведении — вкл/выкл.
   • Всегда поверх других окон — окно не теряется при
     перетаскивании файлов из проводника.
   • Запоминать размер и позицию окна — при следующем
     запуске окно откроется там же, где ты его оставил.

ГОРЯЧИЕ КЛАВИШИ

  Esc         — закрыть активное окно
  Enter / OK  — подтвердить в диалогах

ОСОБЕННОСТИ

  • Многостраничный TIFF и анимированный GIF сохраняются
    постранично: имя_1.png, имя_2.png, имя_3.png ...

  • Прозрачность берётся из исходника. Форматы без альфа-
    канала (JPG, BMP) сохраняются как непрозрачный PNG —
    это неизбежно.

  • Большие PSB читаются целиком в память. Если файл
    весит несколько гигабайт — может не хватить RAM.

  • Файл настроек: %APPDATA%\\pngo.json
"""


# ---------------- Тултипы ----------------
class Tooltip:
    _active = None

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None):
        if not settings.get("tooltips", True):
            return
        if Tooltip._active is self:
            return
        Tooltip._active = self
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left",
                 background="#ffffe0", foreground="#222",
                 relief="solid", borderwidth=1,
                 font=("Segoe UI", 9), padx=6, pady=3).pack()

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None
        if Tooltip._active is self:
            Tooltip._active = None


# ---------------- Обработка изображения ----------------
def process_image(img: Image.Image, s: dict) -> Image.Image:
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    if s.get('trim'):
        try:
            bbox = img.getbbox(alpha_only=True)
        except TypeError:
            bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)

    try:
        max_side = max(0, int(s.get('resize_max', 0) or 0))
    except (ValueError, TypeError):
        max_side = 0
    if max_side > 0 and max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)

    if not s.get('transparency', True):
        bg = Image.new('RGBA', img.size, s.get('bg_color', '#ffffff'))
        img = Image.alpha_composite(bg, img).convert('RGB')

    return img


def save_png(img: Image.Image, out: Path, s: dict):
    try:
        level = max(0, min(9, int(s.get('compression', 6))))
    except (ValueError, TypeError):
        level = 6
    img.save(out, 'PNG', compress_level=level)


# ---------------- Имена вывода ----------------
def resolve_output(path: Path, s: dict):
    mode = s.get('overwrite_mode', 'overwrite')
    base = path.stem + (s.get('suffix') or '')
    out = path.with_name(base + '.png')

    if mode == 'overwrite':
        return out, False
    if mode == 'skip':
        return out, out.exists()
    if not out.exists():
        return out, False
    i = 1
    while True:
        cand = path.with_name(f"{base}_{i}.png")
        if not cand.exists():
            return cand, False
        i += 1


def resolve_multiframe_base(path: Path, s: dict):
    mode = s.get('overwrite_mode', 'overwrite')
    base = path.stem + (s.get('suffix') or '')

    if mode == 'overwrite':
        return base
    if mode == 'skip':
        if path.with_name(base + "_1.png").exists():
            return None
        return base
    i = 0
    while True:
        prefix = base if i == 0 else f"{base}_{i}"
        if not path.with_name(prefix + "_1.png").exists():
            return prefix
        i += 1


# ---------------- Конвертация ----------------
def convert(path: str, s: dict) -> str:
    p = Path(path)
    ext = p.suffix.lower()

    try:
        if ext in PSD_EXT:
            from psd_tools import PSDImage
            psd = PSDImage.open(p)
            img = psd.composite()
            if img is None:
                return f"Ошибка {p.name}: пустой документ"

            out, skip = resolve_output(p, s)
            if skip:
                return f"Пропущен (уже есть): {out.name}"
            existed = out.exists()
            img = process_image(img, s)
            save_png(img, out, s)
            return f"{'Перезаписан' if existed else 'Создан'}: {out.name}"

        elif ext in IMG_EXT:
            with Image.open(p) as im:
                frames = getattr(im, 'n_frames', 1)

                if frames > 1:
                    prefix = resolve_multiframe_base(p, s)
                    if prefix is None:
                        return f"Пропущен (уже есть): {p.stem}_*.png"
                    for i, frame in enumerate(ImageSequence.Iterator(im), 1):
                        out = p.with_name(f"{prefix}_{i}.png")
                        save_png(process_image(frame, s), out, s)
                    return f"OK: {prefix}_1..{frames}.png ({frames} стр.)"

                out, skip = resolve_output(p, s)
                if skip:
                    return f"Пропущен (уже есть): {out.name}"
                existed = out.exists()
                save_png(process_image(im, s), out, s)
                return f"{'Перезаписан' if existed else 'Создан'}: {out.name}"

        else:
            return f"Пропущено (неизвестный формат): {p.name}"

    except Exception as e:
        return f"Ошибка {p.name}: {e}"


# ---------------- Диалоги ----------------
def make_dialog(title, width, height, body_widget_builder):
    w = tk.Toplevel(root)
    w.title(title)
    w.geometry(f"{width}x{height}")
    w.transient(root)
    w.grab_set()
    body_widget_builder(w)
    btn = ttk.Button(w, text="OK", width=10, command=w.destroy)
    btn.pack(pady=(0, 12))
    btn.focus_set()
    w.bind("<Escape>", lambda e: w.destroy())
    w.bind("<Return>", lambda e: w.destroy())
    return w


def show_help():
    def build(w):
        frame = ttk.Frame(w)
        frame.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        txt = tk.Text(frame, wrap="word", font=("Segoe UI", 10),
                      relief="flat", background="#fafafa")
        sb = ttk.Scrollbar(frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")

    make_dialog("Помощь", 640, 620, build)


def show_about():
    def build(w):
        ttk.Label(w, text=APP_NAME,
                  font=("Segoe UI", 18, "bold")).pack(pady=(20, 2))
        ttk.Label(w, text=f"Версия {APP_VERSION}",
                  font=("Segoe UI", 10), foreground="#666").pack()

        ttk.Separator(w, orient="horizontal").pack(fill="x", padx=30, pady=14)

        ttk.Label(w,
                  text="Быстрый конвертер PSD / PSB и других\n"
                       "растровых форматов в PNG с прозрачностью.",
                  justify="center", font=("Segoe UI", 10)).pack()

        feats = (
            "• Drag & drop прямо в окно\n"
            "• PSD / PSB с полной прозрачностью\n"
            "• TIFF / JPG / GIF / WEBP / BMP / TGA / ICO и др.\n"
            "• Многостраничные TIFF и анимированный GIF\n"
            "• Настройка прозрачности и цвета фона\n"
            "• Сжатие PNG, ресайз, обрезка пустых краёв\n"
            "• Пропуск / перезапись / автонумерация готовых PNG\n"
            "• Работает на Python без установки библиотек вручную"
        )
        ttk.Label(w, text=feats, justify="left",
                  font=("Segoe UI", 9), foreground="#333").pack(pady=14)

        ttk.Label(w, text=f"© {APP_YEAR} {APP_AUTHOR}",
                  font=("Segoe UI", 9, "italic"),
                  foreground="#888").pack(side="bottom", pady=10)

    make_dialog("О программе", 440, 520, build)


def show_settings():
    w = tk.Toplevel(root)
    w.title("Настройки")
    w.geometry("520x640")
    w.transient(root)
    w.grab_set()
    w.resizable(False, False)

    nb = ttk.Notebook(w)
    nb.pack(fill='both', expand=True, padx=10, pady=(10, 0))

    # === Вкладка: Изображение ===
    tab_img = ttk.Frame(nb, padding=14)
    nb.add(tab_img, text="Изображение")

    ttk.Label(tab_img, text="Прозрачность",
              font=("Segoe UI", 10, "bold")).pack(anchor='w')
    trans_var = tk.BooleanVar(value=settings.get('transparency', True))
    ttk.Radiobutton(tab_img, text="Сохранять прозрачность (альфа-канал)",
                    variable=trans_var, value=True).pack(anchor='w', padx=14, pady=2)

    bg_row = ttk.Frame(tab_img)
    bg_row.pack(anchor='w', padx=0, pady=2)
    ttk.Radiobutton(bg_row, text="Залить фоном:",
                    variable=trans_var, value=False).pack(side='left', padx=(14, 6))
    color_val = [settings.get('bg_color', '#ffffff')]
    color_btn = tk.Button(bg_row, bg=color_val[0], width=4, height=1,
                          relief='solid', borderwidth=1, cursor='hand2')
    color_btn.pack(side='left')

    def pick_color():
        c = colorchooser.askcolor(color=color_val[0], parent=w,
                                  title="Выбор цвета фона")
        if c and c[1]:
            color_val[0] = c[1]
            color_btn.configure(bg=c[1])

    color_btn.configure(command=pick_color)

    ttk.Separator(tab_img, orient='horizontal').pack(fill='x', pady=12)

    ttk.Label(tab_img, text="Сжатие PNG  (0 — быстро, 9 — макс.)",
              font=("Segoe UI", 10, "bold")).pack(anchor='w')
    comp_var = tk.IntVar(value=int(settings.get('compression', 6)))
    ttk.Spinbox(tab_img, from_=0, to=9, textvariable=comp_var,
                width=5).pack(anchor='w', pady=4)

    ttk.Separator(tab_img, orient='horizontal').pack(fill='x', pady=12)

    ttk.Label(tab_img, text="Уменьшить до (макс. сторона, px; 0 — не менять)",
              font=("Segoe UI", 10, "bold")).pack(anchor='w')
    resize_var = tk.StringVar(value=str(settings.get('resize_max', 0)))
    ttk.Entry(tab_img, textvariable=resize_var, width=10).pack(anchor='w', pady=4)

    ttk.Separator(tab_img, orient='horizontal').pack(fill='x', pady=12)

    trim_var = tk.BooleanVar(value=settings.get('trim', False))
    ttk.Checkbutton(tab_img, text="Обрезать пустые (прозрачные) края",
                    variable=trim_var).pack(anchor='w')

    # === Вкладка: Файлы ===
    tab_files = ttk.Frame(nb, padding=14)
    nb.add(tab_files, text="Файлы")

    ttk.Label(tab_files, text="Если PNG с таким именем уже существует:",
              font=("Segoe UI", 10, "bold")).pack(anchor='w')
    mode_var = tk.StringVar(value=settings.get('overwrite_mode', 'overwrite'))
    ttk.Radiobutton(tab_files, text="Перезаписывать",
                    variable=mode_var, value='overwrite').pack(anchor='w', padx=14, pady=2)
    ttk.Radiobutton(tab_files, text="Пропускать (не трогать существующий)",
                    variable=mode_var, value='skip').pack(anchor='w', padx=14, pady=2)
    ttk.Radiobutton(tab_files, text="Автонумерация (_1, _2, …)",
                    variable=mode_var, value='suffix').pack(anchor='w', padx=14, pady=2)

    ttk.Separator(tab_files, orient='horizontal').pack(fill='x', pady=14)

    ttk.Label(tab_files, text="Суффикс к имени файла",
              font=("Segoe UI", 10, "bold")).pack(anchor='w')
    ttk.Label(tab_files, text="Пример:  photo.png  →  photo_out.png",
              foreground='#666', font=("Segoe UI", 9)).pack(anchor='w', pady=(0, 4))
    suff_var = tk.StringVar(value=settings.get('suffix', ''))
    ttk.Entry(tab_files, textvariable=suff_var, width=22).pack(anchor='w')

    # === Вкладка: Интерфейс ===
    tab_ui = ttk.Frame(nb, padding=14)
    nb.add(tab_ui, text="Интерфейс")

    tip_var = tk.BooleanVar(value=settings.get('tooltips', True))
    cb_tips = ttk.Checkbutton(tab_ui,
                              text="Показывать всплывающие подсказки при наведении",
                              variable=tip_var)
    cb_tips.pack(anchor='w', pady=(0, 10))

    top_var = tk.BooleanVar(value=settings.get('topmost', False))
    cb_top = ttk.Checkbutton(tab_ui,
                             text="Всегда поверх других окон",
                             variable=top_var)
    cb_top.pack(anchor='w', pady=(0, 2))
    ttk.Label(tab_ui,
              text="Окно не теряется за проводником при перетаскивании.",
              foreground='#666', font=("Segoe UI", 9)).pack(anchor='w', padx=24)

    geom_var = tk.BooleanVar(value=settings.get('remember_geometry', True))
    cb_geom = ttk.Checkbutton(tab_ui,
                              text="Запоминать размер и позицию окна",
                              variable=geom_var)
    cb_geom.pack(anchor='w', pady=(14, 2))
    ttk.Label(tab_ui,
              text="При следующем запуске окно откроется там же.",
              foreground='#666', font=("Segoe UI", 9)).pack(anchor='w', padx=24)

    Tooltip(cb_tips, "Показывать жёлтые подсказки\nпри наведении на элементы.")
    Tooltip(cb_top,  "Окно всегда будет сверху\nдругих программ.")
    Tooltip(cb_geom, "Сохранять положение и размер окна\nмежду запусками.")

    # Кнопки
    btns = ttk.Frame(w)
    btns.pack(side='bottom', pady=12)

    def apply():
        settings['transparency'] = bool(trans_var.get())
        settings['bg_color'] = color_val[0]
        try:
            settings['compression'] = max(0, min(9, int(comp_var.get())))
        except (ValueError, TypeError):
            settings['compression'] = 6
        try:
            settings['resize_max'] = max(0, int(resize_var.get() or 0))
        except (ValueError, TypeError):
            settings['resize_max'] = 0
        settings['trim'] = bool(trim_var.get())
        settings['overwrite_mode'] = mode_var.get()
        settings['suffix'] = suff_var.get()
        settings['tooltips'] = bool(tip_var.get())
        settings['topmost'] = bool(top_var.get())
        settings['remember_geometry'] = bool(geom_var.get())

        root.attributes('-topmost', settings['topmost'])

        save_settings()
        w.destroy()

    ttk.Button(btns, text="OK", width=10, command=apply).pack(side='left', padx=6)
    ttk.Button(btns, text="Отмена", width=10,
               command=w.destroy).pack(side='left', padx=6)

    w.bind("<Escape>", lambda e: w.destroy())


# ---------------- Пакетная обработка ----------------
working = [False]


def append_log(text):
    log.insert(tk.END, text + "\n")
    log.see(tk.END)


def clear_log():
    log.delete("1.0", tk.END)


def on_drop(event):
    files = root.tk.splitlist(event.data)
    if not files:
        return
    if working[0]:
        append_log("⏳ Уже идёт обработка, дождись завершения…")
        return
    start_batch(files)


def start_batch(files):
    working[0] = True
    snap = dict(settings)

    progress['maximum'] = len(files)
    progress['value'] = 0
    if not progress.winfo_ismapped():
        progress.pack(fill='x', padx=10, pady=(0, 6), before=log)

    def worker():
        for i, f in enumerate(files, 1):
            msg = convert(f, snap)
            root.after(0, lambda m=msg: append_log(m))
            root.after(0, lambda v=i: progress.configure(value=v))
        root.after(0, finish_batch)

    threading.Thread(target=worker, daemon=True).start()


def finish_batch():
    working[0] = False
    log.insert(tk.END, "—" * 46 + "\n")
    log.see(tk.END)
    progress.pack_forget()


# ---------------- Окно ----------------
load_settings()

root = TkinterDnD.Tk()
root.title(f"{APP_NAME} {APP_VERSION}")
root.minsize(480, 340)

if settings.get('remember_geometry') and settings.get('geometry'):
    try:
        root.geometry(settings['geometry'])
    except Exception:
        root.geometry("580x460")
else:
    root.geometry("580x460")

if settings.get('topmost'):
    root.attributes('-topmost', True)

style = ttk.Style()
try:
    style.theme_use("vista")
except tk.TclError:
    pass

# Тулбар
toolbar = ttk.Frame(root, padding=(8, 6))
toolbar.pack(fill='x')

btn_settings = ttk.Button(toolbar, text="⚙  Настройки", command=show_settings)
btn_settings.pack(side='left')

btn_help = ttk.Button(toolbar, text="❓  Помощь", command=show_help)
btn_help.pack(side='left', padx=(6, 0))

btn_about = ttk.Button(toolbar, text="ℹ  О программе", command=show_about)
btn_about.pack(side='left', padx=(6, 0))

btn_clear = ttk.Button(toolbar, text="🗑  Очистить лог", command=clear_log)
btn_clear.pack(side='right')

# Подсказка
hint = ttk.Label(root,
                 text="Перетащи сюда PSD / PSB / TIFF / JPG / GIF / …",
                 font=("Segoe UI", 12))
hint.pack(pady=(4, 6))

# Лог
log = tk.Text(root, height=14, font=("Consolas", 9),
              bg="#111", fg="#0f0", insertbackground="#0f0",
              relief="flat", padx=8, pady=6)
log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

# Прогресс-бар (скрыт)
progress = ttk.Progressbar(root, mode='determinate')

# Тултипы
Tooltip(btn_settings, "Настройки программы:\nпрозрачность, сжатие, ресайз,\n"
                      "правила перезаписи, суффикс.")
Tooltip(btn_help,     "Инструкция и список\nподдерживаемых форматов.")
Tooltip(btn_about,    "Информация о программе,\nверсия и автор.")
Tooltip(btn_clear,    "Очистить журнал операций.")
Tooltip(hint,         "Перетащи файлы мышкой прямо сюда.\nМожно сразу несколько.")
Tooltip(log,          "Журнал операций:\nчто создано, перезаписано или пропущено.")

# Приветствие в логе
log.insert(tk.END, f"{APP_NAME} {APP_VERSION} готов к работе.\n")
log.insert(tk.END, "Перетащи файлы в окно — они появятся здесь.\n")
log.insert(tk.END, "—" * 46 + "\n")

# Drag & Drop
root.drop_target_register(DND_FILES)
root.dnd_bind('<<Drop>>', on_drop)


def on_close():
    if settings.get('remember_geometry'):
        try:
            settings['geometry'] = root.geometry()
            save_settings()
        except Exception:
            pass
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_close)

root.mainloop()