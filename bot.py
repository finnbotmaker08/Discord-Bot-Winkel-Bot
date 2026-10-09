import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import urllib.parse
import random

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID") or 0)
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "1556668456315781321")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "JOUW_CLIENT_SECRET_HIER")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8080/callback")
PORT = int(os.getenv("PORT", 8080))

if not TOKEN:
    print("❌ CRITICHE FOUT: Geen DISCORD_TOKEN gevonden!")
    exit(1)

SERVERNAAM = "Finns Bots"
KLEUR = 0x5865F2
STAFF_ROL = "Staff"
LID_ROL_ID = 1557808209924726889
NOT_VERIFIED_ROL_ID = 1557808209924726890
KLANT_ROL = "Klant"
PREMIUM_KLANT_ROL = "💎 Premium Klant"
TICKET_CATEGORIE = "🎫 ┃ BESTELLEN & SUPPORT"

MEDEDELING_KANAAL_ID = 1556575385284648980
SHUTDOWN_ROL_ID = 1556578093081305159

SHUTDOWN_ALLOWED_ROLES = [
    1556578093081305159,
    1556578106347618344,
    1556578110609031179,
    1556578107354521760,
    1556578916825825300
]

SHOP_BESTAND = Path(__file__).with_name("shop_data.json")

VASTE_PRODUCTEN = [
    {
        "id": 1,
        "naam": "Security Bot",
        "omschrijving": "Automoderatie, kick, ban, mute, warn, clear, slowmode, lockdown, unlock, suggestie.",
        "prijs": 7.50
    },
    {
        "id": 2,
        "naam": "Normale Bot",
        "omschrijving": "Een bot met 10 custom commands.",
        "prijs": 10.00
    },
    {
        "id": 3,
        "naam": "Premium Bot",
        "omschrijving": "Premium bot met 15 custom commands en Security Bot inbegrepen.",
        "prijs": 15.00
    }
]

STANDAARD_SHOP_DATA = {
    "producten": VASTE_PRODUCTEN,
    "bestellingen": [],
    "kortingscodes": {"OPENING": 25},
    "blacklist": [],
    "volgend_product": 4,
    "volgende_bestelling": 1
}

REGELS = [
    "Wees respectvol tegen iedereen binnen de community.",
    "Geen spam, ongevraagde reclame of ongepaste inhoud.",
]

ACTIEVE_PUZZELS = {}
VERWERKTE_CODES = set()


def embed(titel, beschrijving=None):
    e = discord.Embed(title=titel, description=beschrijving, colour=KLEUR)
    e.set_footer(text=SERVERNAAM)
    return e


def euro(bedrag):
    tekst = f"{bedrag:,.2f}"
    return "€" + tekst.replace(",", "_").replace(".", ",").replace("_", ".")


def laad_shop():
    data = STANDAARD_SHOP_DATA
    if SHOP_BESTAND.exists():
        try:
            geladen = json.loads(SHOP_BESTAND.read_text(encoding="utf-8"))
            if isinstance(geladen, dict):
                data = geladen
                data["producten"] = VASTE_PRODUCTEN
                if "blacklist" not in data:
                    data["blacklist"] = []
        except Exception:
            pass
    return data


def bewaar_shop():
    SHOP_BESTAND.write_text(json.dumps(SHOP, ensure_ascii=False, indent=2), encoding="utf-8")


SHOP = laad_shop()
if not SHOP_BESTAND.exists():
    bewaar_shop()


def vind_product_id(product_id):
    return next((p for p in SHOP["producten"] if p["id"] == product_id), None)


def vind_bestelling(bestelling_id):
    return next((b for b in SHOP["bestellingen"] if b["id"] == bestelling_id), None)


def is_staff(member):
    return member.guild_permissions.administrator or any(r.name == STAFF_ROL for r in member.roles)


async def staff_check(interaction):
    if is_staff(interaction.user):
        return True
    await interaction.response.send_message("Alleen staffleden hebben hier toegang toe.", ephemeral=True)
    return False


class VerifieerOAuthKnop(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verifieer via OAuth2 & Puzzel", emoji="🧩", style=discord.ButtonStyle.success, custom_id="oauth_verifieer_knop")
    async def verifieer(self, interaction: discord.Interaction, button: discord.ui.Button):
        parsed_uri = urllib.parse.urlparse(REDIRECT_URI)
        base_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}" if parsed_uri.netloc else "http://localhost:8080"
        puzzel_url = f"{base_url}/puzzel"
        
        e = embed(
            "🧩 Verificatie Puzzel",
            f"Klik op de onderstaande link om de puzzel op te lossen en je rol te ontvangen:\n\n"
            f"👉 [Los de Puzzel op]({puzzel_url})"
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


async def handle_puzzel(request):
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    juiste_antwoord = a + b
    
    import uuid
    sessie_id = str(uuid.uuid4())
    ACTIEVE_PUZZELS[sessie_id] = str(juiste_antwoord)

    puzzel_html = (
        "<html><head><title>Verificatie Puzzel</title></head>"
        "<body style='background:#1e1f22; color:#fff; font-family:sans-serif; text-align:center; padding-top:80px;'>"
        "<div style='background:#2b2d31; display:inline-block; padding:40px; border-radius:10px;'>"
        "<h2 style='color:#5865F2;'>🧠 Beveiligingspuzzel</h2>"
        f"<p>Hoeveel is {a} + {b}?</p>"
        "<form action='/puzzel_check' method='get'>"
        f"<input type='hidden' name='sessie' value='{sessie_id}'>"
        "<input type='text' name='antwoord' placeholder='Antwoord...' style='padding:10px; text-align:center;' required>"
        "<br><br><button type='submit' style='background:#57F287; padding:10px 20px;'>Verstuur</button>"
        "</form></div></body></html>"
    )
    return web.Response(text=puzzel_html, content_type="text/html")


async def handle_puzzel_check(request):
    sessie_id = request.query.get("sessie", "")
    antwoord = request.query.get("antwoord", "").strip()
    verwacht_antwoord = ACTIEVE_PUZZELS.get(sessie_id)

    if sessie_id in ACTIEVE_PUZZELS:
        del ACTIEVE_PUZZELS[sessie_id]

    if verwacht_antwoord and antwoord == verwacht_antwoord:
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds.join"
        }
        auth_url = f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}"
        raise web.HTTPFound(auth_url)
    else:
        fail_html = "<html><body style='background:#1e1f22; color:#fff; text-align:center; padding-top:100px;'><h1>❌ Onjuist!</h1></body></html>"
        return web.Response(text=fail_html, content_type="text/html")


async def handle_oauth_callback(request):
    code = request.query.get("code")
    if not code:
        return web.Response(text="❌ Geen code ontvangen.", status=400)

    if code in VERWERKTE_CODES:
        success_html = "<html><body style='background:#1e1f22; color:#fff; text-align:center; padding-top:100px;'><h1 style='color:#57F287;'>Verificatie voltooid!</h1><p>U kunt het web sluiten en verder gaan in discord.</p></body></html>"
        return web.Response(text=success_html, content_type="text/html")

    VERWERKTE_CODES.add(code)

    token_url = "https://discord.com/api/oauth2/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    bot_instance = request.app["bot"]

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data, headers=headers) as resp:
            if resp.status != 200:
                return web.Response(text="Fout bij token ophalen", status=400)
            token_json = await resp.json()
            access_token = token_json.get("access_token")

        user_url = "https://discord.com/api/users/@me"
        auth_header = {"Authorization": f"Bearer {access_token}"}
        async with session.get(user_url, headers=auth_header) as resp:
            if resp.status != 200:
                return web.Response(text="Kon profiel niet ophalen", status=400)
            user_data = await resp.json()

    user_id = int(user_data["id"])
    guild = bot_instance.get_guild(GUILD_ID)
    if not guild:
        return web.Response(text="Server niet gevonden", status=500)

    member = guild.get_member(user_id)
    if not member:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            return web.Response(text="Word eerst lid van de server!", status=400)

    lid_rol = guild.get_role(LID_ROL_ID)
    not_verified_rol = guild.get_role(NOT_VERIFIED_ROL_ID)

    try:
        if lid_rol:
            await member.add_roles(lid_rol)
        if not_verified_rol and not_verified_rol in member.roles:
            await member.remove_roles(not_verified_rol)
    except Exception as e:
        print(f"Rollen fout: {e}")

    success_html = "<html><head><title>Verificatie Voltooid</title></head><body style='background:#1e1f22; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;'><div style='background:#2b2d31; display:inline-block; padding:40px; border-radius:10px;'><h1 style='color:#57F287;'>Verificatie voltooid!</h1><p style='font-size:18px; margin-top:20px;'>U kunt het web sluiten en verder gaan in discord.</p></div></body></html>"
    return web.Response(text=success_html, content_type="text/html")


class FinnsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix="m?", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifieerOAuthKnop())
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.clear_commands(guild=guild)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        print("✅ Commando's gesynchroniseerd.")

        self.web_app = web.Application()
        self.web_app["bot"] = self
        self.web_app.router.add_get("/puzzel", handle_puzzel)
        self.web_app.router.add_get("/puzzel_check", handle_puzzel_check)
        self.web_app.router.add_get("/callback", handle_oauth_callback)
        
        self.runner = web.AppRunner(self.web_app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "0.0.0.0", PORT)
        await self.site.start()
        print(f"🌐 Webserver gestart op poort {PORT}")

    async def on_ready(self):
        print(f"🤖 Ingelogd als {self.user}")


client = FinnsBot()
client.run(TOKEN)
