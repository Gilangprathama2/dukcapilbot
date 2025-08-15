# -*- coding: utf-8 -*-
"""
Bot Layanan Dispendukcapil Kota Semarang
Fitur:
- Menu utama + submenu (InlineKeyboard)
- Deteksi teks bebas (keyword + sinonim)
- Jawaban rapi (Markdown) + emoji
- Stabil di Railway (error handler, limit panjang pesan, drop_pending_updates)

Jika di-host di Railway:
- Tambah Variable: BOT_TOKEN = <token bot>
- Procfile: worker: python main.py
"""

import os
import logging
from typing import Dict, List, Tuple, Callable
from dataclasses import dataclass

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MessageEntity,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================================
# KONFIGURASI DASAR
# =========================================================
TOKEN = os.environ.get("BOT_TOKEN", "8340296681:AAGQPOEdkYsQHBmf-c51_SxUX3YzXJptlLE")

SIDNOK_URL = "https://sidnok.semarangkota.go.id/"
JAM_BUKA = (
    "🕒 *Jam Operasional Dispendukcapil Pusat*\n"
    "• Senin–Kamis: 08.15–15.00 WIB\n"
    "• Jumat: 08.00–13.00 WIB\n"
    "• Sabtu & Minggu: Libur"
)
ALAMAT = (
    "📍 *Alamat Kantor Pusat*\n"
    "Jl. Kanguru Raya No.3, Gayamsari, Kec. Gayamsari,\n"
    "Kota Semarang, Jawa Tengah 50248"
)
CATATAN = (
    "ℹ️ *Catatan*: Informasi ini bersifat umum. "
    "Untuk verifikasi berkas/keputusan akhir, silakan menuju loket Dispendukcapil."
)

MAX_TG = 4096  # batas karakter pesan Telegram


# =========================================================
# LOGGING & ERROR HANDLER
# =========================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("dukcapil-bot")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tangani error tanpa crash."""
    log.exception("Exception in handler:", exc_info=context.error)
    try:
        if isinstance(update, Update):
            target = update.effective_message
            if target:
                await target.reply_text(
                    "⚠️ Maaf, sedang ada gangguan. Coba lagi sebentar ya.",
                    disable_web_page_preview=True,
                )
    except Exception:
        pass


# =========================================================
# UTIL
# =========================================================
def chunk_message(text: str, limit: int = MAX_TG) -> List[str]:
    """Bagi pesan panjang jadi beberapa bagian <= 4096 char."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        cut = text.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
    return chunks


def normalize(s: str) -> str:
    return (s or "").lower().strip()


def any_in(text: str, keywords: List[str]) -> bool:
    t = normalize(text)
    return any(k in t for k in keywords)


# =========================================================
# KONTEN: TEKS STANDAR & TEMPLATE
# =========================================================
HOME_TEXT = (
    "👋 *Selamat datang di Asisten Layanan Dispendukcapil Kota Semarang!*\n\n"
    "Saya siap bantu info layanan berikut:\n"
    "• KTP (baru, hilang, ubah data, masa berlaku)\n"
    "• KK (ubah alamat/pekerjaan/status/golongan darah, gabung/pisah, hilang)\n"
    "• Akta Kelahiran & Akta Kematian\n"
    "• KIA Anak\n"
    "• Pindah/Kedatangan Domisili\n"
    "• Jam & Alamat Kantor\n"
    "• Layanan Online via *Sidnok*\n\n"
    "Pilih menu di bawah atau *ketik bebas* pertanyaanmu."
)

ABOUT_TEXT = (
    "ℹ️ *Tentang Bot*\n"
    "Asisten informasi layanan Dispendukcapil Kota Semarang.\n"
    "Gunakan menu tombol atau ketik bebas pertanyaan Anda.\n\n"
    f"{CATATAN}"
)

FAQ_TEXT = (
    "🧭 *Menu Bantuan / FAQ*\n"
    "Contoh yang bisa diketik:\n"
    "• `ktp hilang`, `ktp baru`, `ubah data ktp`, `masa berlaku ktp`\n"
    "• `kk hilang`, `kk ubah alamat`, `kk ubah pekerjaan`, `kk status`, `kk golongan darah`, `gabung kk`, `pisah kk`\n"
    "• `akta kelahiran`, `akta kelahiran hilang`\n"
    "• `akta kematian`, `akta kematian hilang`\n"
    "• `kia`, `pindah domisili`, `pendatang masuk`\n"
    "• `jam`, `alamat`, `sidnok`"
)

# --- Detail jawaban per sub-layanan ---
DETAILS: Dict[str, str] = {
    # KTP
    "ktp_baru": (
        "📄 *KTP Baru*\n"
        "• Fotokopi KK & Akta Kelahiran\n"
        "• Usia minimal 17 tahun\n"
        f"• Proses di kantor Dispendukcapil atau via *Sidnok* ({SIDNOK_URL})\n\n"
        f"{CATATAN}"
    ),
    "ktp_hilang": (
        "🧾 *KTP Hilang*\n"
        "1️⃣ Lapor kehilangan di kepolisian\n"
        "2️⃣ Bawa laporan ke Dispendukcapil untuk cetak ulang\n"
        "3️⃣ Siapkan KK & data diri\n\n"
        f"{CATATAN}"
    ),
    "ktp_ubah": (
        "✏️ *Ubah Data KTP*\n"
        "• Siapkan dokumen pendukung sesuai perubahan (Akta/KK/Buku Nikah, dsb.)\n"
        "• Bawa KTP & KK asli\n\n"
        f"{CATATAN}"
    ),
    "ktp_perpanjang": (
        "🔄 *Masa Berlaku KTP*\n"
        "• e-KTP berlaku *seumur hidup*\n"
        "• Update diperlukan hanya jika ada *perubahan data*\n\n"
        f"{CATATAN}"
    ),

    # KK
    "kk_hilang": (
        "🧾 *KK Hilang*\n"
        "• Lapor kehilangan ke kepolisian\n"
        "• Bawa laporan ke Dispendukcapil untuk cetak ulang\n\n"
        f"{CATATAN}"
    ),
    "kk_alamat": (
        "🏠 *Ubah Alamat di KK*\n"
        "• KK & KTP asli\n"
        "• Surat pindah\n"
        "• (Jika diminta) bukti kepemilikan/kontrak rumah\n\n"
        f"{CATATAN}"
    ),
    "kk_pekerjaan": (
        "💼 *Ubah Pekerjaan di KK*\n"
        "• SK/Surat keterangan dari instansi (jika PNS/Guru/dll)\n"
        "• KTP & KK asli\n\n"
        f"{CATATAN}"
    ),
    "kk_status": (
        "💍 *Ubah Status Perkawinan*\n"
        "• Buku nikah / akta cerai\n"
        "• KK & KTP kedua pihak\n\n"
        f"{CATATAN}"
    ),
    "kk_goldar": (
        "🅾️ *Ubah Golongan Darah di KK*\n"
        "• Surat keterangan golongan darah (PMI/RS/lab)\n"
        "• KK & KTP asli\n\n"
        f"{CATATAN}"
    ),
    "kk_gabung": (
        "👨‍👩‍👧 *Gabung KK*\n"
        "• KK asli & pengantar RT/RW\n"
        "• Proses verifikasi di kantor\n\n"
        f"{CATATAN}"
    ),
    "kk_pisah": (
        "🧍 *Pisah KK*\n"
        "• KK asli & pengantar RT/RW\n"
        "• Formulir pemisahan akan dibantu di loket\n\n"
        f"{CATATAN}"
    ),

    # Akta
    "akta_lahir_umum": (
        "📜 *Akta Kelahiran*\n"
        "• Surat keterangan lahir (RS/Bidan)\n"
        "• KK & KTP orang tua\n"
        "• Buku nikah (jika ada)\n"
        f"• Bisa melalui kantor Dispendukcapil atau *Sidnok* ({SIDNOK_URL})"
    ),
    "akta_lahir_hilang": (
        "🧾 *Akta Kelahiran Hilang*\n"
        "• Lapor kehilangan ke kepolisian\n"
        "• Bawa laporan & dokumen ke Dispendukcapil untuk penerbitan ulang\n\n"
        f"{CATATAN}"
    ),
    "akta_mati_umum": (
        "⚰️ *Akta Kematian*\n"
        "• Surat keterangan kematian (RS/bidan/kelurahan)\n"
        "• KK & KTP almarhum\n"
        "• KTP pelapor\n"
        "• Ajukan di kantor Dispendukcapil atau kanal resmi yang tersedia"
    ),
    "akta_mati_hilang": (
        "🧾 *Akta Kematian Hilang*\n"
        "• Lapor kehilangan ke kepolisian\n"
        "• Ajukan ulang di Dispendukcapil\n\n"
        f"{CATATAN}"
    ),

    # Pindah / Datang
    "pindah_keluar": (
        "🚚 *Perpindahan Keluar*\n"
        "• KK & KTP\n"
        "• Surat pengantar RT/RW ➜ terbit *surat pindah*\n\n"
        f"{CATATAN}"
    ),
    "pendatang_masuk": (
        "📦 *Pendatang Masuk (Perpindahan Masuk)*\n"
        "• Surat pindah dari kota asal\n"
        "• KK & KTP untuk pembuatan domisili baru\n\n"
        f"{CATATAN}"
    ),

    # Info & Online
    "jam": JAM_BUKA,
    "alamat": ALAMAT,
    "sidnok": f"🌐 *Sidnok Online*\nPengajuan KTP/KK/Akta via: {SIDNOK_URL}",
}

# =========================================================
# KEYWORD & SINONIM UNTUK MODE KETIK BEBAS
# =========================================================
KW = {
    "ktp_hilang": ["ktp hilang", "kehilangan ktp", "ktp ilang"],
    "ktp_baru": ["ktp baru", "buat ktp", "daftar ktp", "pembuatan ktp"],
    "ktp_ubah": ["ubah ktp", "koreksi ktp", "ganti data ktp", "perubahan ktp"],
    "ktp_perpanjang": ["perpanjang ktp", "masa berlaku ktp", "ktp expired", "ktp mati"],
    "kk_hilang": ["kk hilang", "kehilangan kk", "kk ilang"],
    "kk_alamat": ["ubah alamat kk", "pindah alamat kk", "alamat kk"],
    "kk_pekerjaan": ["pekerjaan kk", "ubah pekerjaan kk", "ganti pekerjaan kk"],
    "kk_status": ["status kk", "ubah status kk", "nikah kk", "cerai kk"],
    "kk_goldar": ["golongan darah kk", "goldar kk", "gologan darah kk", "g.darah kk"],
    "kk_gabung": ["gabung kk", "penggabungan kk", "join kk"],
    "kk_pisah": ["pisah kk", "pemisahan kk"],
    "akta_lahir_umum": ["akta kelahiran", "buat akta lahir"],
    "akta_lahir_hilang": ["akta kelahiran hilang", "kehilangan akta kelahiran"],
    "akta_mati_umum": ["akta kematian", "buat akta kematian"],
    "akta_mati_hilang": ["akta kematian hilang", "kehilangan akta kematian"],
    "kia": ["kia", "kartu identitas anak"],
    "pindah_keluar": ["pindah domisili", "surat pindah", "pindah keluar"],
    "pendatang_masuk": ["pendatang", "kedatangan", "masuk domisili", "datang"],
    "jam": ["jam", "buka", "operasional"],
    "alamat": ["alamat", "lokasi", "kantor dimana", "dimana"],
    "sidnok": ["sidnok", "online dukcapil", "layanan online", "online ktp", "online kk", "online akta"],
    "faq": ["menu", "faq", "help", "bantuan", "panduan"],
}

# =========================================================
# MENU & SUBMENU (INLINE KEYBOARD)
# =========================================================
def kb_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📄 KTP", callback_data="menu_ktp"),
            InlineKeyboardButton("🏠 KK", callback_data="menu_kk"),
        ],
        [
            InlineKeyboardButton("📜 Akta Kelahiran", callback_data="menu_akta_lahir"),
            InlineKeyboardButton("⚰️ Akta Kematian", callback_data="menu_akta_mati"),
        ],
        [
            InlineKeyboardButton("🧒 KIA Anak", callback_data="menu_kia"),
            InlineKeyboardButton("🚚 Pindah / Datang", callback_data="menu_pindah"),
        ],
        [
            InlineKeyboardButton("🕒 Jam & Alamat", callback_data="menu_info"),
            InlineKeyboardButton("🌐 Sidnok Online", url=SIDNOK_URL),
        ],
        [
            InlineKeyboardButton("📚 FAQ/Menu Bantuan", callback_data="menu_faq"),
        ],
    ])


def kb_ktp() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 KTP Baru", callback_data="ktp_baru")],
        [InlineKeyboardButton("🧾 KTP Hilang", callback_data="ktp_hilang")],
        [InlineKeyboardButton("✏️ Ubah Data KTP", callback_data="ktp_ubah")],
        [InlineKeyboardButton("🔄 Masa Berlaku KTP", callback_data="ktp_perpanjang")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="home")],
    ])


def kb_kk() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Ubah Alamat KK", callback_data="kk_alamat")],
        [InlineKeyboardButton("💼 Ubah Pekerjaan KK", callback_data="kk_pekerjaan")],
        [InlineKeyboardButton("💍 Ubah Status KK", callback_data="kk_status")],
        [InlineKeyboardButton("🅾️ Ubah Golongan Darah", callback_data="kk_goldar")],
        [InlineKeyboardButton("👨‍👩‍👧 Gabung KK", callback_data="kk_gabung")],
        [InlineKeyboardButton("🧍 Pisah KK", callback_data="kk_pisah")],
        [InlineKeyboardButton("🧾 KK Hilang", callback_data="kk_hilang")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="home")],
    ])


def kb_akta_lahir() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Akta Lahir Hilang", callback_data="akta_lahir_hilang")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="home")],
    ])


def kb_akta_mati() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Akta Kematian Hilang", callback_data="akta_mati_hilang")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="home")],
    ])


def kb_kia() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Kembali", callback_data="home")],
    ])


def kb_pindah() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚚 Perpindahan Keluar", callback_data="pindah_keluar")],
        [InlineKeyboardButton("📦 Pendatang Masuk", callback_data="pendatang_masuk")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="home")],
    ])


def kb_info() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Sidnok", url=SIDNOK_URL)],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="home")],
    ])


def kb_faq() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Kembali", callback_data="home")],
    ])


# =========================================================
# RESPON MENU
# =========================================================
def ans_home() -> Tuple[str, InlineKeyboardMarkup]:
    return HOME_TEXT, kb_home()


def ans_ktp() -> Tuple[str, InlineKeyboardMarkup]:
    return "📄 *Layanan KTP* — pilih topik:", kb_ktp()


def ans_kk() -> Tuple[str, InlineKeyboardMarkup]:
    return "🏠 *Layanan KK* — pilih topik:", kb_kk()


def ans_akta_lahir() -> Tuple[str, InlineKeyboardMarkup]:
    return DETAILS["akta_lahir_umum"], kb_akta_lahir()


def ans_akta_mati() -> Tuple[str, InlineKeyboardMarkup]:
    return DETAILS["akta_mati_umum"], kb_akta_mati()


def ans_kia() -> Tuple[str, InlineKeyboardMarkup]:
    return (
        "🧒 *KIA (Kartu Identitas Anak)*\n"
        "• Akta Kelahiran\n"
        "• KK\n"
        "• KTP orang tua\n"
        "• Pas foto 3×4 anak",
        kb_kia()
    )


def ans_pindah() -> Tuple[str, InlineKeyboardMarkup]:
    return "🚚 *Pindah/Kedatangan Domisili* — pilih:", kb_pindah()


def ans_info() -> Tuple[str, InlineKeyboardMarkup]:
    return f"{JAM_BUKA}\n\n{ALAMAT}", kb_info()


def ans_faq() -> Tuple[str, InlineKeyboardMarkup]:
    return FAQ_TEXT, kb_faq()


MENUS: Dict[str, Callable[[], Tuple[str, InlineKeyboardMarkup]]] = {
    "home": ans_home,
    "menu_ktp": ans_ktp,
    "menu_kk": ans_kk,
    "menu_akta_lahir": ans_akta_lahir,
    "menu_akta_mati": ans_akta_mati,
    "menu_kia": ans_kia,
    "menu_pindah": ans_pindah,
    "menu_info": ans_info,
    "menu_faq": ans_faq,
}


# =========================================================
# MODE KETIK BEBAS (NLP SEDERHANA)
# =========================================================
def answer_free_text(user_text: str) -> str:
    t = normalize(user_text)

    # urutan cek dari yang spesifik ke umum
    # KTP
    if any_in(t, KW["ktp_hilang"]):
        return DETAILS["ktp_hilang"]
    if any_in(t, KW["ktp_baru"]) or ("ktp" in t and any_in(t, ["baru", "buat", "daftar", "pembuatan"])):
        return DETAILS["ktp_baru"]
    if any_in(t, KW["ktp_perpanjang"]):
        return DETAILS["ktp_perpanjang"]
    if "ktp" in t and any_in(t, ["ubah", "koreksi", "ganti", "perubahan"]):
        return DETAILS["ktp_ubah"]

    # KK
    if any_in(t, KW["kk_hilang"]):
        return DETAILS["kk_hilang"]
    if any_in(t, KW["kk_alamat"]):
        return DETAILS["kk_alamat"]
    if any_in(t, KW["kk_pekerjaan"]):
        return DETAILS["kk_pekerjaan"]
    if any_in(t, KW["kk_status"]):
        return DETAILS["kk_status"]
    if any_in(t, KW["kk_goldar"]):
        return DETAILS["kk_goldar"]
    if any_in(t, KW["kk_gabung"]):
        return DETAILS["kk_gabung"]
    if any_in(t, KW["kk_pisah"]):
        return DETAILS["kk_pisah"]

    # Akta
    if any_in(t, KW["akta_lahir_hilang"]):
        return DETAILS["akta_lahir_hilang"]
    if any_in(t, KW["akta_lahir_umum"]):
        return DETAILS["akta_lahir_umum"]
    if any_in(t, KW["akta_mati_hilang"]):
        return DETAILS["akta_mati_hilang"]
    if any_in(t, KW["akta_mati_umum"]):
        return DETAILS["akta_mati_umum"]

    # KIA
    if any_in(t, KW["kia"]):
        # gunakan teks dari ans_kia
        return ans_kia()[0]

    # Pindah / Datang
    if any_in(t, KW["pindah_keluar"]):
        return DETAILS["pindah_keluar"]
    if any_in(t, KW["pendatang_masuk"]):
        return DETAILS["pendatang_masuk"]

    # Sidnok / Info
    if any_in(t, KW["sidnok"]):
        return DETAILS["sidnok"]
    if any_in(t, KW["jam"]):
        return DETAILS["jam"]
    if any_in(t, KW["alamat"]):
        return DETAILS["alamat"]

    # FAQ/Help
    if any_in(t, KW["faq"]):
        return FAQ_TEXT

    # Fallback
    return (
        "❓ *Maaf, saya belum mengenali pertanyaan itu.*\n"
        "Coba ketik salah satu contoh: `ktp hilang`, `kk ubah alamat`, `akta kelahiran`, `kia`, `pindah domisili`, `sidnok`.\n"
        "Atau buka *Menu* lewat perintah /menu."
    )


# =========================================================
# HANDLERS
# =========================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, kb = ans_home()
    for part in chunk_message(text):
        await update.message.reply_text(
            part, parse_mode=ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True
        )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, kb = ans_home()
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, kb = ans_faq()
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ABOUT_TEXT, parse_mode=ParseMode.MARKDOWN)


async def cmd_sidnok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(DETAILS["sidnok"], parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{JAM_BUKA}\n\n{ALAMAT}", parse_mode=ParseMode.MARKDOWN)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    try:
        if data in MENUS:
            text, kb = MENUS[data]()
            # edit message bila memungkinkan, kalau gagal kirim baru
            try:
                await q.edit_message_text(
                    text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True
                )
            except Exception:
                await q.message.reply_text(
                    text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True
                )
        elif data in DETAILS:
            txt = DETAILS[data]
            for part in chunk_message(txt):
                try:
                    await q.edit_message_text(part, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
                except Exception:
                    await q.message.reply_text(part, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        else:
            await q.answer("Menu tidak dikenali.", show_alert=False)
    except Exception as e:
        log.exception("Callback error: %s", e)
        await q.answer("Terjadi gangguan. Coba lagi ya.", show_alert=True)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    # catat jika ada link/mention (biar siap kalau nanti dipakai)
    _ = [e for e in (update.message.entities or []) if e.type in (MessageEntity.URL, MessageEntity.MENTION)]
    try:
        ans = answer_free_text(text)
        for part in chunk_message(ans):
            await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except Exception as e:
        log.exception("Message error: %s", e)
        await update.message.reply_text(
            "⚠️ Terjadi gangguan. Silakan coba lagi.", parse_mode=ParseMode.MARKDOWN
        )


# =========================================================
# MAIN
# =========================================================
def build_app() -> Application:
    app: Application = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(False)  # lebih stabil di plan gratis
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("sidnok", cmd_sidnok))
    app.add_handler(CommandHandler("info", cmd_info))

    # Callback (tombol)
    app.add_handler(CallbackQueryHandler(on_callback))

    # Text bebas
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Error global
    app.add_error_handler(error_handler)

    return app


def main():
    app = build_app()
    log.info("Bot berjalan…")
    # drop_pending_updates=True biar saat restart tidak banjir update lama
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
