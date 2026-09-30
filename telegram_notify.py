"""Envoi des notifications sur Telegram (remplace les webhooks Discord).

Variables Railway nécessaires :
  TELEGRAM_BOT_TOKEN  jeton du bot donné par @BotFather (ex : 123456789:AAE...)
  TELEGRAM_CHAT_ID    identifiant du groupe Telegram (ex : -1001234567890)
"""
import html
import os
import re
import time

import requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip().removeprefix("bot")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"
MAX_LEN = 3800   # limite Telegram : 4096 caractères par message


def _safe(err):
    """Message d'erreur sans le jeton (les erreurs réseau contiennent l'adresse complète)."""
    return str(err).replace(TOKEN, "<jeton>") if TOKEN else str(err)


def check():
    """Vérifie le jeton et le groupe au démarrage ; renvoie une ligne claire pour les logs."""
    if not TOKEN:
        return "❌ Variable TELEGRAM_BOT_TOKEN absente sur Railway."
    try:
        me = requests.get(f"{API}/getMe", timeout=15).json()
        if not me.get("ok"):
            return f"❌ Jeton Telegram refusé ({me.get('description')}). Vérifie TELEGRAM_BOT_TOKEN."
        bot = "@" + me["result"]["username"]
        if not CHAT_ID:
            return f"❌ Bot {bot} OK, mais la variable TELEGRAM_CHAT_ID est absente.\n{_groupes_vus()}"
        chat = requests.get(f"{API}/getChat", params={"chat_id": CHAT_ID}, timeout=15).json()
        if not chat.get("ok"):
            return (f"❌ Bot {bot} OK, mais groupe {CHAT_ID} introuvable ({chat.get('description')}). "
                    f"Ajoute le bot au groupe et vérifie TELEGRAM_CHAT_ID.\n{_groupes_vus()}")
        return f"✅ Telegram : bot {bot} → groupe « {chat['result'].get('title', CHAT_ID)} »"
    except Exception as e:
        return f"❌ Telegram injoignable : {_safe(e)}"


def _groupes_vus():
    """Groupes où le bot a été ajouté ou a reçu un message ces dernières 24 h : pour trouver TELEGRAM_CHAT_ID."""
    try:
        ups = requests.get(f"{API}/getUpdates", params={"timeout": 0}, timeout=15).json().get("result", [])
    except Exception:
        return ""
    seen = {}
    for u in ups:
        for k in ("message", "my_chat_member", "channel_post"):
            c = (u.get(k) or {}).get("chat") or {}
            if c.get("type") in ("group", "supergroup", "channel"):
                seen[c["id"]] = c.get("title", "")
        status = (u.get("my_chat_member") or {}).get("new_chat_member", {}).get("status")
        if status in ("left", "kicked"):                 # le bot a été retiré de ce groupe
            seen.pop(u["my_chat_member"]["chat"]["id"], None)
    if not seen:
        return "   Aucun groupe vu : ajoute le bot à ton groupe, écris « salut », puis redémarre (Restart)."
    return "\n".join(f"   Groupe « {t} » : mets TELEGRAM_CHAT_ID = {i}" for i, t in seen.items())


def md_to_html(text):
    """Markdown « façon Discord » (**gras**, [lien](url), ## titre, * liste) vers le HTML de Telegram."""
    t = html.escape(text or "", quote=False)
    t = re.sub(r"```(?:\w+\n)?(.*?)```", r"<pre>\1</pre>", t, flags=re.S)
    t = re.sub(r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", "━━━━━━━━━━", t)   # séparateur --- lisible
    t = re.sub(r"(?m)^#{1,6}\s*(.+?)\s*$", r"<b>\1</b>", t)
    t = re.sub(r"(?m)^(\s*)[\*\-]\s+", r"\1• ", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    t = re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])", r"<i>\1</i>", t)
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    return t


def _plain(text):
    """Secours si Telegram refuse le HTML : on enlève la mise en forme."""
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", text or "")
    return re.sub(r"[*`#]", "", t)


def _chunks(text):
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > MAX_LEN:                 # ligne géante : coupée net
            parts.append(line[:MAX_LEN])
            line = line[MAX_LEN:]
        if cur and len(cur) + len(line) + 1 > MAX_LEN:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    return parts + ([cur] if cur else [])


def _refus(r):
    try:
        return r.json().get("description", r.text[:200])
    except ValueError:
        return r.text[:200]


def _params(r):
    try:
        return r.json().get("parameters") or {}
    except ValueError:
        return {}


def _post(method, fields, files=None, timeout=20):
    """Envoi avec deux rattrapages : groupe devenu « supergroupe » (Telegram change alors son
    identifiant) et trop de messages d'un coup (Telegram dit combien attendre)."""
    global CHAT_ID
    for _ in range(3):
        payload = {**fields, "chat_id": CHAT_ID}
        if files:
            r = requests.post(f"{API}/{method}", data=payload, files=files, timeout=timeout)
        else:
            r = requests.post(f"{API}/{method}", json=payload, timeout=timeout)
        p = _params(r)
        if p.get("migrate_to_chat_id"):
            CHAT_ID = str(p["migrate_to_chat_id"])
            print(f"(Le groupe Telegram a changé d'identifiant : mets TELEGRAM_CHAT_ID = {CHAT_ID} sur Railway)")
            continue
        if r.status_code == 429:
            time.sleep(int(p.get("retry_after", 5)) + 1)
            continue
        return r
    return r


def send_text(markdown_text):
    ok = True
    for part in _chunks(markdown_text or ""):
        try:
            r = _post("sendMessage", {"text": md_to_html(part), "parse_mode": "HTML",
                                      "link_preview_options": {"is_disabled": True}})
            if r.status_code == 400 and "parse" in _refus(r).lower():   # mise en forme refusée : texte simple
                r = _post("sendMessage", {"text": _plain(part)[:4096]})
            if not r.ok:
                ok = False
                print(f"(Message refusé par Telegram : {r.status_code} {_refus(r)})")
        except Exception as e:
            ok = False
            print(f"(Telegram injoignable : {_safe(e)})")
        time.sleep(1)
    return ok


def send_embed(embed):
    """Ancienne « fiche » Discord (titre, lien, description, champs, pied) mise en un message Telegram."""
    lines = []
    title = embed.get("title", "")
    if embed.get("url"):
        lines.append(f"**[{title}]({embed['url']})**")
    elif title:
        lines.append(f"**{title}**")
    if embed.get("description"):
        lines += ["", embed["description"]]
    for f in embed.get("fields", []):
        lines += ["", f"**{f.get('name', '')}**", f.get("value", "")]
    if embed.get("footer", {}).get("text"):
        lines += ["", f"*{embed['footer']['text']}*"]
    return send_text("\n".join(lines))


def send_file(filename, data, caption=""):
    try:
        r = _post("sendDocument", {"caption": _plain(caption)[:1024]},
                  files={"document": (filename, data, "application/pdf")}, timeout=60)
        if not r.ok:
            print(f"(Envoi du fichier refusé par Telegram : {r.status_code} {_refus(r)})")
        return r.ok
    except Exception as e:
        print(f"(Telegram injoignable pour le fichier : {_safe(e)})")
        return False
