import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import urllib.parse

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web

# Laad de .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID") or 0)
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "JOUW_CLIENT_ID_HIER")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "JOUW_CLIENT_SECRET_HIER")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "https://discord-bot-winkel-bot-production.up.railway.app/callback")
PORT = int(os.getenv("PORT", 8080))

if not TOKEN:
    print("❌ CRITICHE FOUT: Geen DISCORD_TOKEN gevonden in het .env bestand!")
    exit(1)

# --------------------------------------------------------------------------
# Instellingen & Configuratie
# --------------------------------------------------------------------------
SERVERNAAM = "Finns Bots"
KLEUR = 0x5865F2
STAFF_ROL = "Staff"
LID_ROL = "Lid"
KLANT_ROL = "Klant"
PREMIUM_KLANT_ROL = "💎 Premium Klant"
NOT_VERIFIED_ROL = "Not-Verified"
NOT_VERIFIED_ROL_ID = 1557808209924726890
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
        "omschrijving": "Automoderatie, kick, ban, mute, warn, clear, slowmode, lockdown, unlock, suggestie. + Een tutorial hoe je alles moet downloaden en installeren zit erbij. Wij zullen de eerste dag berijkbaar zijn voor onderhoud daarna niet meer. Je krijgt een speciale rol om free release mee te pakken en extra tips.",
        "prijs": 7.50
    },
    {
        "id": 2,
        "naam": "Normale Bot",
        "omschrijving": "Een bot met 10 custom commands. Een tutorial hoe je alles moet downloaden en installeren zit erbij. Wij zullen de eerste 3 dagen berijkbaar zijn voor onderhoud daarna niet meer. Je krijgt een speciale rol om free release mee te pakken en extra tips.",
        "prijs": 10.00
    },
    {
        "id": 3,
        "naam": "Premium Bot",
        "omschrijving": "Premium bot. Je kan 15 custom commands kiezen, Security Bot zit erbij. Een tutorial hoe je alles moet downloaden en installeren + hoe je het 24/7 moet hostenzit erbij. Wij zullen de eerste week berijkbaar zijn voor onderhoud daarna niet meer. Je kan de bot hosten op je eigen pc voor 24/7, de bot gaat zolang mee als je wilt. Je krijgt ook een speciale rol om free release mee te pakken en extra tips.",
        "prijs": 15.00
    }
]

STANDAARD_SHOP_DATA = {
    "producten": VASTE_PRODUCTEN,
    "bestellingen": [],
    "kortingscodes": {
        "OPENING": 25
    },
    "blacklist": [],
    "volgend_product": 4,
    "volgende_bestelling": 1
}

REGELS = [
    "Wees respectvol tegen iedereen binnen de community.",
    "Geen spam, ongevraagde reclame of ongepaste inhoud.",
    "Bestel en betaal uitsluitend via een beveiligd ticket in #koop-een-bot.",
    "Volg ten alle tijden de instructies van het staffteam op.",
    "Gebruik kanalen waarvoor ze specifiek bedoeld zijn.",
]
# --------------------------------------------------------------------------


def embed(titel, beschrijving=None):
    e = discord.Embed(title=titel, description=beschrijving, colour=KLEUR)
    e.set_footer(text=SERVERNAAM)
    return e


def welkom_embed():
    return embed(
        f"Welkom bij {SERVERNAAM}! 🤖",
        "Hier vind je de meest professionele custom Discord-bots voor jouw server.\n\n"
        "📦 Bekijk ons assortiment in **#bot-aanbod**\n"
        "💶 Bekijk de prijzen in **#prijzen-en-pakketten**\n"
        "🎫 Direct bestellen? Open een ticket via **#koop-een-bot**\n"
        "❓ Vragen of hulp nodig? Ga naar **#vragen-en-support**",
    )


def regels_embed():
    tekst = "\n".join(f"**{i}.** {regel}" for i, regel in enumerate(REGELS, 1))
    return embed("📜 Serverregels", tekst)


def verificatie_embed():
    return embed(
        "🔒 Veilige OAuth2 Verificatie",
        "Welkom! Om volledige toegang te krijgen tot de server, dien je de beveiligde OAuth2 verificatie te doorlopen.\n\n"
        "🛡️ **Wat controleert het systeem?**\n"
        "• Je account moet minimaal **3 dagen oud** zijn (alt-account preventie).\n"
        "• Je mag niet op de server blacklist staan.\n\n"
        "Klik op de knop hieronder om in te loggen via Discord en te verifiëren."
    )


STATUS_ICOON = {"open": "🟡", "afgerond": "🟢", "geannuleerd": "🔴"}


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


def vind_product(naam):
    naam = naam.lower().strip()
    for p in SHOP["producten"]:
        if p["naam"].lower() == naam:
            return p
    for p in SHOP["producten"]:
        if naam in p["naam"].lower():
            return p
    return None


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


async def product_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=p["naam"][:100], value=p["naam"][:100])
        for p in SHOP["producten"]
        if current.lower() in p["naam"].lower()
    ][:25]


def maak_bestelling(user, product, procent, code, ticket_kanaal_id):
    prijs = round(product["prijs"] * (100 - procent) / 100, 2)
    b = {
        "id": SHOP["volgende_bestelling"],
        "gebruiker_id": user.id,
        "gebruiker_naam": user.display_name,
        "product_id": product["id"],
        "product_naam": product["naam"],
        "originele_prijs": product["prijs"],
        "prijs": prijs,
        "korting_procent": procent,
        "korting_code": code,
        "status": "open",
        "ticket_kanaal_id": ticket_kanaal_id,
        "aangemaakt": discord.utils.utcnow().isoformat(),
        "review": False,
    }
    SHOP["volgende_bestelling"] += 1
    SHOP["bestellingen"].append(b)
    bewaar_shop()
    return b


def product_embed(p):
    e = embed(p["naam"], p["omschrijving"])
    e.add_field(name="Prijs", value=euro(p["prijs"]))
    return e


def bestelling_embed(b, titel):
    kleur = {"open": 0xFEE75C, "afgerond": 0x57F287, "geannuleerd": 0xED4245}[b["status"]]
    e = discord.Embed(title=titel, colour=kleur)
    e.add_field(name="Klant", value=f"<@{b['gebruiker_id']}>")
    e.add_field(name="Product", value=b["product_naam"])
    if b["korting_procent"]:
        prijs = f"~~{euro(b['originele_prijs'])}~~ **{euro(b['prijs'])}** ({b['korting_procent']}% korting met `{b['korting_code']}`)"
    else:
        prijs = f"**{euro(b['prijs'])}**"
    e.add_field(name="Prijs", value=prijs, inline=False)
    e.add_field(name="Status", value=f"{STATUS_ICOON[b['status']]} {b['status']}")
    e.set_footer(text=SERVERNAAM)
    return e


async def log_bestelling(guild, e):
    kanaal = discord.utils.get(guild.text_channels, name="order-logs")
    if kanaal:
        await kanaal.send(embed=e)


def bots_embed(titel="🤖 Ons Bot-assortiment"):
    if not SHOP["producten"]:
        return embed(titel, "Momenteel zijn er geen producten beschikbaar.")
    e = embed(titel, "Ontdek onze hoogwaardige custom bots en pakketten:")
    for p in SHOP["producten"]:
        e.add_field(name=f"{p['naam']}", value=f"Prijs: **{euro(p['prijs'])}**\n_{p['omschrijving']}_", inline=False)
    return e


def prijzen_embed():
    if not SHOP["producten"]:
        return embed("💶 Prijzenlijst", "Geen producten gevonden.")
    e = embed("💶 Prijzenlijst", "Transparante prijzen voor al onze diensten en bots:")
    for p in SHOP["producten"]:
        e.add_field(name=f"{p['naam']}", value=f"**{euro(p['prijs'])}**\n{p['omschrijving']}", inline=False)
    return e


def help_embed(staff=False):
    e = embed(
        "📖 Bot Commando's Overzicht",
        "`/shop`  open de winkel en bekijk de bots\n"
        "`/bots`  bekijk direct alle beschikbare bots\n"
        "`/prijzen`  bekijk het prijzenoverzicht\n"
        "`/bestellen`  scroll door het menu en open direct een bestelticket\n"
        "`/mijnbestellingen`  bekijk jouw aankoopgeschiedenis\n"
        "`/review`  plaats een review na een afgeronde order\n"
        "`/serverinfo`  bekijk statistieken van de server\n"
        "`/ping`  test de reactiesnelheid van de bot",
    )
    if staff:
        e.add_field(
            name="🔒 Staff Beheerdersmenu",
            value=(
                "`/bestellingen`  openstaande bestellingen inzien\n"
                "`/afronden`  bestelling afronden & klant-rol toekennen\n"
                "`/annuleren`  bestelling annuleren\n"
                "`/serverwipe`  wist alle berichten, behoudt kanalen & reset rollen naar Not-Verified\n"
                "`/product_toevoegen`, `/product_bewerken`, `/product_verwijderen`\n"
                "`/blacklist`, `/verwijderblacklist`\n"
                "`/kortingscode_maken`, `/kortingscodes`, `/kortingscode_verwijderen`\n"
                "`/shopstats`  gedetailleerde omzet en statistieken\n"
                "`/maakserver`, `/shutdown`, `/startup`, `/verificatie-setup`"
            ),
            inline=False,
        )
    return e


# --------------------------------------------------------------------------
# OAuth2 Verificatie UI & Webserver Koppeling
# --------------------------------------------------------------------------
class VerifieerOAuthKnop(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verifieer via OAuth2", emoji="🔗", style=discord.ButtonStyle.success, custom_id="oauth_verifieer_knop")
    async def verifieer(self, interaction: discord.Interaction, button: discord.ui.Button):
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds.join"
        }
        auth_url = f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}"
        
        e = embed(
            "🔐 Beveiligde Verificatie Link",
            f"Klik op onderstaande knop om je Discord-account te verifiëren via onze beveiligde OAuth2 portal.\n\n"
            f"👉 [Klik hier om in te loggen en te verifiëren]({auth_url})"
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


# --------------------------------------------------------------------------
# AIOHTTP Webserver voor OAuth2 Callback Afhandeling
# --------------------------------------------------------------------------
async def handle_oauth_callback(request):
    code = request.query.get("code")
    if not code:
        return web.Response(text="❌ Fout: Geen autorisatiecode ontvangen van Discord.", status=400)

    forwarded_proto = request.headers.get("X-Forwarded-Proto", "https")
    forwarded_host = request.headers.get("X-Forwarded-Host", request.host)
    dynamic_redirect_uri = f"{forwarded_proto}://{forwarded_host}/callback"

    token_url = "https://discord.com/api/oauth2/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI if "localhost" not in REDIRECT_URI else dynamic_redirect_uri,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    bot_instance = request.app["bot"]

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data, headers=headers) as resp:
            if resp.status != 200:
                resp_text = await resp.text()
                return web.Response(text=f"❌ Fout bij het verifiëren van je tokens bij Discord: {resp_text}", status=400)
            token_json = await resp.json()
            access_token = token_json.get("access_token")

        user_url = "https://discord.com/api/users/@me"
        auth_header = {"Authorization": f"Bearer {access_token}"}
        async with session.get(user_url, headers=auth_header) as resp:
            if resp.status != 200:
                return web.Response(text="❌ Kon je Discord-profiel niet ophalen.", status=400)
            user_data = await resp.json()

    user_id = int(user_data["id"])
    guild = bot_instance.get_guild(GUILD_ID)

    if not guild:
        return web.Response(text="❌ Server niet gevonden door de bot.", status=500)

    member = guild.get_member(user_id)
    if not member:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            return web.Response(text="❌ Je zit nog niet in de Discord-server! Word eerst lid en probeer het opnieuw.", status=400)

    if user_id in SHOP.get("blacklist", []):
        html_fail = "<h3>❌ Verificatie Mislukt</h3><p>Dit account staat op de blacklist van deze server.</p>"
        return web.Response(text=html_fail, content_type="text/html")

    nu = datetime.now(timezone.utc)
    leeftijd_dagen = (nu - member.created_at).days
    if leeftijd_dagen < 3:
        html_fail = f"<h3>❌ Verificatie Mislukt</h3><p>Je Discord-account is te nieuw ({leeftijd_dagen} dagen oud). Minimaal vereist is 3 dagen.</p>"
        return web.Response(text=html_fail, content_type="text/html")

    lid_rol = discord.utils.get(guild.roles, name=LID_ROL)
    not_verified_rol = guild.get_role(NOT_VERIFIED_ROL_ID) if NOT_VERIFIED_ROL_ID else discord.utils.get(guild.roles, name=NOT_VERIFIED_ROL)

    try:
        if lid_rol:
            await member.add_roles(lid_rol)
        if not_verified_rol and not_verified_rol in member.roles:
            await member.remove_roles(not_verified_rol)
        
        mod_logs = discord.utils.get(guild.text_channels, name="mod-logs")
        if mod_logs:
            e = embed("✅ OAuth2 Verificatie Geslaagd", f"Gebruiker {member.mention} (`{member.id}`) is succesvol geverifieerd via OAuth2.")
            e.add_field(name="Account Leeftijd", value=f"{leeftijd_dagen} dagen")
            await mod_logs.send(embed=e)

    except Exception as e:
        print(f"Fout bij toewijzen rollen via OAuth2: {e}")
        return web.Response(text="❌ Er is een fout opgetreden bij het toekennen van je rollen.", status=500)

    success_html = """
    <html>
        <head><title>Verificatie Geslaagd</title></head>
        <body style="background:#1e1f22; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;">
            <h1 style="color:#57F287;">✅ Verificatie Geslaagd!</h1>
            <p>Je bent succesvol geverifieerd voor de server. Je kunt dit tabblad sluiten en terugkeren naar Discord.</p>
        </body>
    </html>
    """
    return web.Response(text=success_html, content_type="text/html")


class BestelSelect(discord.ui.Select):
    def __init__(self):
        opties = [
            discord.SelectOption(
                label=p["naam"][:100],
                description=f"{euro(p['prijs'])} - {p['omschrijving'][:80]}"[:100],
                value=str(p["id"]),
            )
            for p in SHOP["producten"][:25]
        ]
        super().__init__(placeholder="📜 Scroll en selecteer een gewenst pakket...", options=opties)

    async def callback(self, interaction: discord.Interaction):
        product = vind_product_id(int(self.values[0]))
        if product is None:
            await interaction.response.send_message("Dit product is inmiddels niet meer beschikbaar.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=product_embed(product), view=KoopDezeKnop(product["id"]), ephemeral=True
        )


class BestelShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.add_item(BestelSelect())


class KoopDezeKnop(discord.ui.View):
    def __init__(self, product_id):
        super().__init__(timeout=300)
        self.product_id = product_id

    @discord.ui.button(label="Koop deze", emoji="🛒", style=discord.ButtonStyle.success)
    async def koop_deze(self, interaction: discord.Interaction, button: discord.ui.Button):
        product = vind_product_id(self.product_id)
        if product is None:
            await interaction.response.send_message("Dit product is niet meer beschikbaar.", ephemeral=True)
            return
        await maak_ticket(interaction, product)


async def maak_ticket(interaction: discord.Interaction, product=None, code=None):
    guild = interaction.guild
    user = interaction.user

    for ch in guild.text_channels:
        if ch.topic == f"ticket:{user.id}":
            await interaction.response.send_message(f"Je hebt al een actief ticket geopend: {ch.mention}", ephemeral=True)
            return

    procent, gebruikte_code = 0, None
    if code:
        sleutel = code.strip().upper()
        if sleutel not in SHOP["kortingscodes"]:
            await interaction.response.send_message("De opgegeven kortingscode is ongeldig.", ephemeral=True)
            return
        procent, gebruikte_code = SHOP["kortingscodes"][sleutel], sleutel

    staff = discord.utils.get(guild.roles, name=STAFF_ROL)
    toegang = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, read_message_history=True, attach_files=True
    )

    categorie = discord.utils.get(guild.categories, name=TICKET_CATEGORIE)
    if categorie is None:
        cat_overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            staff: discord.PermissionOverwrite(view_channel=True, send_messages=True) if staff else discord.PermissionOverwrite()
        }
        categorie = await guild.create_category(TICKET_CATEGORIE, overwrites=cat_overwrites)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: toegang,
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    if staff:
        overwrites[staff] = toegang

    kanaal = await guild.create_text_channel(
        f"ticket-{user.name}",
        category=categorie,
        topic=f"ticket:{user.id}",
        overwrites=overwrites,
    )

    if product:
        b = maak_bestelling(user, product, procent, gebruikte_code, kanaal.id)
        e = bestelling_embed(b, f"🛒 Bestelling #{b['id']}")
        e.description = (
            f"Welkom {user.mention}! Bedankt voor je bestelling. Een medewerker neemt zo snel mogelijk contact met je op voor de betaling en levering.\n\n"
            f"*Staff: gebruik `/afronden {b['id']}` zodra de afhandeling voltooid is.*"
        )
        await log_bestelling(guild, bestelling_embed(b, f"🆕 Nieuwe bestelling #{b['id']}"))
    else:
        e = embed(
            "🎫 Support Ticket",
            f"Welkom {user.mention}! Laat ons weten waar we je mee kunnen helpen. Ons supportteam reageert zo spoedig mogelijk.",
        )
    ping = staff.mention if staff else ""
    
    if interaction.response.is_done():
        await interaction.followup.send(f"Je ticket is aangemaakt: {kanaal.mention}", ephemeral=True)
    else:
        await interaction.response.send_message(f"Je ticket is aangemaakt: {kanaal.mention}", ephemeral=True)

    await kanaal.send(content=f"{user.mention} {ping}", embed=e, view=SluitKnop())


class TicketKnop(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open een ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="ticket_openen")
    async def openen(self, interaction: discord.Interaction, button: discord.ui.Button):
        await maak_ticket(interaction)


class SluitKnop(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket sluiten", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_sluiten")
    async def sluiten(self, interaction: discord.Interaction, button: discord.ui.Button):
        kanaal = interaction.channel
        staff = discord.utils.get(interaction.guild.roles, name=STAFF_ROL)
        is_eigenaar = kanaal.topic == f"ticket:{interaction.user.id}"
        is_staff_lid = staff in interaction.user.roles if staff else False
        
        if not (is_eigenaar or is_staff_lid or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("Je hebt geen rechten om dit ticket te sluiten.", ephemeral=True)
            return
            
        await interaction.response.send_message("🔒 Dit ticket wordt over 5 seconden automatisch gesloten...")
        await asyncio.sleep(5)
        await kanaal.delete()


# --------------------------------------------------------------------------
# Bot Hoofdklasse, Anti-Raid & Webserver Startup
# --------------------------------------------------------------------------
class FinnsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix="m?", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifieerOAuthKnop())
        self.add_view(TicketKnop())
        self.add_view(SluitKnop())
        
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        print("✅ Slash commando's succesvol gesynchroniseerd.")

        self.web_app = web.Application()
        self.web_app["bot"] = self
        self.web_app.router.add_get("/callback", handle_oauth_callback)
        self.web_app.router.add_get("/", lambda r: web.Response(text="Bot OAuth2 webserver is online!", content_type="text/html"))
        
        self.runner = web.AppRunner(self.web_app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "0.0.0.0", PORT)
        await self.site.start()
        print(f"🌐 OAuth2 webserver gestart op poort {PORT}")

    async def on_ready(self):
        await self.change_presence(activity=discord.Game(name="Bots verkopen | /help"))
        print(f"🤖 Ingelogd als {self.user} (ID: {self.user.id})")

    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        not_verified_rol = guild.get_role(NOT_VERIFIED_ROL_ID) if NOT_VERIFIED_ROL_ID else discord.utils.get(guild.roles, name=NOT_VERIFIED_ROL)
        if not_verified_rol:
            try:
                await member.add_roles(not_verified_rol)
            except discord.Forbidden:
                print("Kan de rol Not-Verified niet toekennen: zet de bot-rol hoger in de lijst.")

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        totaal_tags = len(message.raw_mentions) + len(message.raw_role_mentions)

        if totaal_tags >= 5:
            now = datetime.now(timezone.utc)
            try:
                await message.delete()

                if isinstance(message.author, discord.Member):
                    try:
                        await message.author.timeout(
                            now + timedelta(days=7),
                            reason="Anti-Raid: 5+ tags in één bericht gedetecteerd"
                        )
                    except discord.Forbidden:
                        print("⚠️ Kan geen timeout geven: De bot-rol staat te laag in de hiërarchie.")
                    except Exception as e:
                        print(f"Timeout fout: {e}")

                mod_logs = discord.utils.get(message.guild.text_channels, name="mod-logs")
                if mod_logs:
                    datum_tijd = now.strftime("%d-%m-%Y om %H:%M:%S UTC")
                    e = embed("🚨 Anti-Raid / Spam Actie Onderdoken", "Er is automatische actie ondernomen tegen een tag-raid.")
                    e.add_field(name="Gebruiker", value=f"{message.author.mention} (`{message.author.name}`)", inline=True)
                    e.add_field(name="User ID", value=f"`{message.author.id}`", inline=True)
                    e.add_field(name="Datum & Tijd", value=datum_tijd, inline=True)
                    e.add_field(name="Kanaal", value=message.channel.mention, inline=True)
                    e.add_field(name="Poging / Inhoud", value=f"```{message.content[:900]}```", inline=False)
                    e.colour = 0xED4245
                    await mod_logs.send(embed=e)
            except Exception as ex:
                print(f"Fout in anti-raid systeem: {ex}")

        await self.process_commands(message)


client = FinnsBot()
tree = client.tree


@client.event
async def on_app_command_completion(interaction: discord.Interaction, command: app_commands.Command):
    if interaction.guild:
        log_kanaal = discord.utils.get(interaction.guild.text_channels, name="bot-activiteit")
        if log_kanaal:
            kanaal_info = interaction.channel.mention if interaction.channel else "Onbekend kanaal"
            e = embed(
                "📝 Commando Uitgevoerd",
                f"**Gebruiker:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"**Commando:** `/{command.name}`\n"
                f"**Kanaal:** {kanaal_info}"
            )
            await log_kanaal.send(embed=e)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
@tree.command(name="help", description="Toon alle beschikbare commando's")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=help_embed(is_staff(interaction.user)), ephemeral=True)


@tree.command(name="bots", description="Bekijk al onze beschikbare bots")
async def bots_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=bots_embed())


@tree.command(name="prijzen", description="Bekijk de prijzenlijst")
async def prijzen_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=prijzen_embed())


@tree.command(name="bestellen", description="Scroll door producten en open direct een bestelticket")
async def bestellen_cmd(interaction: discord.Interaction):
    if not SHOP["producten"]:
        await interaction.response.send_message("Er zijn momenteel geen producten beschikbaar om te bestellen.", ephemeral=True)
        return
    e = embed("🛒 Bot Bestellen", "Selecteer hieronder het gewenste product in het menu om je bestelling te starten:")
    await interaction.response.send_message(embed=e, view=BestelShopView(), ephemeral=True)


@tree.command(name="serverinfo", description="Informatie over deze server")
async def serverinfo_cmd(interaction: discord.Interaction):
    g = interaction.guild
    e = embed(f"ℹ️ {g.name}")
    e.add_field(name="Leden", value=str(g.member_count))
    e.add_field(name="Kanalen", value=str(len(g.channels)))
    e.add_field(name="Aangemaakt op", value=discord.utils.format_dt(g.created_at, "D"))
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    await interaction.response.send_message(embed=e)


@tree.command(name="ping", description="Test de reactiesnelheid van de bot")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! Latency is {round(client.latency * 1000)} ms")


@tree.command(name="verificatie-setup", description="Plaats het verificatiepaneel in het kanaal (Alleen Eigenaar)")
async def verificatie_setup_cmd(interaction: discord.Interaction):
    if interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Alleen de **servereigenaar** kan dit commando uitvoeren.", ephemeral=True)
        return

    await interaction.channel.send(embed=verificatie_embed(), view=VerifieerOAuthKnop())
    await interaction.response.send_message("✅ Verificatiepaneel succesvol geplaatst!", ephemeral=True)


@tree.command(name="setup_embeds", description="Plaats welkomst- en infobereichten in de kanalen (admin)")
@app_commands.default_permissions(administrator=True)
async def setup_embeds_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    g = interaction.guild

    doelen = {
        "verificatie": (verificatie_embed(), VerifieerOAuthKnop()),
        "welkom": (welkom_embed(), None),
        "server-regels": (regels_embed(), None),
        "bot-aanbod": (bots_embed(), None),
        "prijzen-en-pakketten": (prijzen_embed(), None),
        "koop-een-bot": (
            embed("🛒 Bot Bestellen", "Klik op de knop hieronder om direct een beveiligd bestel-ticket te openen."),
            TicketKnop(),
        ),
    }

    geplaatst, ontbreekt = [], []
    for naam, (e, view) in doelen.items():
        kanaal = discord.utils.get(g.text_channels, name=naam)
        if kanaal is None:
            ontbreekt.append(naam)
            continue
        if view:
            await kanaal.send(embed=e, view=view)
        else:
            await kanaal.send(embed=e)
        geplaatst.append(f"#{naam}")

    tekst = "Berichten succesvol geplaatst in: " + ", ".join(geplaatst) if geplaatst else "Geen berichten geplaatst."
    if ontbreekt:
        tekst += "\nNiet gevonden kanalen: " + ", ".join(f"#{n}" for n in ontbreekt)
    await interaction.followup.send(tekst, ephemeral=True)


# --------------------------------------------------------------------------
# Server Lockdown, Maakserver & Serverwipe
# --------------------------------------------------------------------------
def mag_shutdown(member) -> bool:
    return any(rol.id == SHUTDOWN_ROL_ID for rol in member.roles)


@tree.command(name="shutdown", description="Zet de server hermetisch op slot (Admin)")
async def shutdown_cmd(interaction: discord.Interaction):
    if not mag_shutdown(interaction.user):
        await interaction.response.send_message("Geen toestemming.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    for category in guild.categories:
        try:
            await category.edit(sync_permissions=False)
            await category.set_permissions(guild.default_role, read_messages=False, view_channel=False, connect=False)
            for role_id in SHUTDOWN_ALLOWED_ROLES:
                role = guild.get_role(role_id)
                if role:
                    await category.set_permissions(role, read_messages=True, view_channel=True, send_messages=True, connect=True, speak=True)
        except Exception:
            pass

    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        try:
            if channel.id == MEDEDELING_KANAAL_ID:
                await channel.edit(sync_permissions=False)
                await channel.set_permissions(guild.default_role, read_messages=True, view_channel=True, send_messages=False, connect=False)
            else:
                await channel.edit(sync_permissions=False)
                await channel.set_permissions(guild.default_role, read_messages=False, view_channel=False, connect=False)
                for role_id in SHUTDOWN_ALLOWED_ROLES:
                    role = guild.get_role(role_id)
                    if role:
                        await channel.set_permissions(role, read_messages=True, view_channel=True, send_messages=True, connect=True, speak=True)
        except Exception:
            pass

    await interaction.followup.send("🚨 **Server Lockdown is geactiveerd!**", ephemeral=True)


@tree.command(name="startup", description="Heft de shutdown op (Admin)")
async def startup_cmd(interaction: discord.Interaction):
    if not mag_shutdown(interaction.user):
        await interaction.response.send_message("Geen toestemming.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    for category in guild.categories:
        try:
            await category.set_permissions(guild.default_role, read_messages=None, view_channel=None, connect=None)
        except Exception:
            pass

    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        try:
            await channel.set_permissions(guild.default_role, read_messages=None, view_channel=None, connect=None, send_messages=None)
        except Exception:
            pass

    await interaction.followup.send("✅ **Server Startup is voltooid!**", ephemeral=True)


@tree.command(name="serverwipe", description="Wist alle berichten, behoudt kanalen en zet rollen terug naar Not-Verified (Admin)")
async def serverwipe_cmd(interaction: discord.Interaction):
    if not mag_shutdown(interaction.user):
        await interaction.response.send_message("Geen toestemming om dit commando uit te voeren.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    not_verified_rol = guild.get_role(NOT_VERIFIED_ROL_ID) if NOT_VERIFIED_ROL_ID else discord.utils.get(guild.roles, name=NOT_VERIFIED_ROL)
    staff_rol = discord.utils.get(guild.roles, name=STAFF_ROL)

    for member in guild.members:
        if member.bot:
            continue
        if staff_rol and staff_rol in member.roles:
            continue
        if member.guild_permissions.administrator:
            continue

        try:
            te_verwijderen = [r for r in member.roles if r != guild.default_role and r.name != NOT_VERIFIED_ROL]
            if te_verwijderen:
                await member.remove_roles(*te_verwijderen)
            if not_verified_rol and not_verified_rol not in member.roles:
                await member.add_roles(not_verified_rol)
        except Exception:
            pass

    for channel in list(guild.text_channels):
        try:
            category = channel.category
            overwrites = channel.overwrites
            name = channel.name
            topic = channel.topic
            slowmode = channel.slowmode_delay
            nsfw = channel.is_nsfw()

            await channel.delete()
            await guild.create_text_channel(
                name,
                category=category,
                overwrites=overwrites,
                topic=topic,
                slowmode_delay=slowmode,
                nsfw=nsfw
            )
        except Exception:
            pass

    await interaction.followup.send("💥 **Server Wipe voltooid!** Alle kanalen zijn behouden, alle berichten zijn gewist en leden zijn teruggezet naar Not-Verified.", ephemeral=True)


@tree.command(name="maakserver", description="Wist alles, maakt rollen en stelt alle permissies perfect in (Admin)")
async def maakserver_cmd(interaction: discord.Interaction):
    if not mag_shutdown(interaction.user):
        await interaction.response.send_message("Geen toestemming om dit commando uit te voeren.", ephemeral=True)
        return

    await interaction.response.send_message("⚙️ Bezig met het opnieuw instellen van de serverstructuur...", ephemeral=True)
    guild = interaction.guild

    for channel in list(guild.channels):
        try:
            await channel.delete()
        except Exception:
            pass

    staff_rol_obj = discord.utils.get(guild.roles, name=STAFF_ROL)
    if not staff_rol_obj:
        try:
            staff_rol_obj = await guild.create_role(name=STAFF_ROL, color=discord.Color.red())
        except Exception:
            pass

    lid_rol_obj = discord.utils.get(guild.roles, name=LID_ROL)
    if not lid_rol_obj:
        try:
            lid_rol_obj = await guild.create_role(name=LID_ROL, color=discord.Color.blue())
        except Exception:
            pass

    klant_rol_obj = discord.utils.get(guild.roles, name=KLANT_ROL)
    if not klant_rol_obj:
        try:
            klant_rol_obj = await guild.create_role(name=KLANT_ROL, color=discord.Color.green())
        except Exception:
            pass

    premium_klant_rol_obj = discord.utils.get(guild.roles, name=PREMIUM_KLANT_ROL)
    if not premium_klant_rol_obj:
        try:
            premium_klant_rol_obj = await guild.create_role(name=PREMIUM_KLANT_ROL, color=discord.Color.gold())
        except Exception:
            pass

    not_verified_rol_obj = guild.get_role(NOT_VERIFIED_ROL_ID) if NOT_VERIFIED_ROL_ID else discord.utils.get(guild.roles, name=NOT_VERIFIED_ROL)
    if not not_verified_rol_obj:
        try:
            not_verified_rol_obj = await guild.create_role(name=NOT_VERIFIED_ROL, color=discord.Color.dark_grey())
        except Exception:
            pass

    structuur = {
        "👑 ┃ ALGEMENE INFORMATIE": [
            ("verificatie", "text", False, True, False),
            ("welkom", "text", False, False, False),
            ("server-regels", "text", False, False, False),
            ("aankondigingen", "text", False, False, False),
            ("giveaways", "text", False, False, False),
            ("kies-rollen", "text", False, False, False),
            ("faq", "text", False, False, False),
        ],
        "🛒 ┃ WINKEL & ASSORTIMENT": [
            ("bot-aanbod", "text", False, False, False),
            ("prijzen-en-pakketten", "text", False, False, False),
            ("actieve-kortingen", "text", False, False, False),
            ("klanten-reviews", "text", False, False, False),
        ],
        "💎 ┃ EXCLUSIEF & PREMIUM": [
            ("free-releases", "text", False, False, True),
            ("tips-en-trics", "text", False, False, True),
        ],
        "🎫 ┃ BESTELLEN & SUPPORT": [
            ("koop-een-bot", "text", False, False, False),
            ("vragen-en-support", "text", False, False, False),
            ("suggesties-en-ideeën", "text", False, False, False),
            ("bug-rapportage", "text", False, False, False),
        ],
        "💬 ┃ COMMUNITY HOEK": [
            ("algemene-chat", "text", False, False, False),
            ("bot-commands", "text", False, False, False),
            ("media-en-showcase", "text", False, False, False),
            ("gezelligheid", "text", False, False, False),
            ("poll-en-stemmingen", "text", False, False, False),
        ],
        "📚 ┃ DOCUMENTATIE & TUTORIALS": [
            ("handleidingen", "text", False, False, False),
            ("hosting-tips", "text", False, False, False),
            ("nuttige-links", "text", False, False, False),
        ],
        "🔐 ┃ STAFF ZONE": [
            ("staff-overleg", "text", True, False, False),
            ("order-logs", "text", True, False, False),
            ("bot-activiteit", "text", True, False, False),
            ("mod-logs", "text", True, False, False),
            ("beheerders-paneel", "text", True, False, False),
        ]
    }

    for cat_naam, kanalen in structuur.items():
        try:
            if "STAFF" in cat_naam:
                cat_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                }
                if staff_rol_obj:
                    cat_overwrites[staff_rol_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                categorie = await guild.create_category(cat_naam, overwrites=cat_overwrites)
            elif "EXCLUSIEF" in cat_naam:
                cat_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                }
                if premium_klant_rol_obj:
                    cat_overwrites[premium_klant_rol_obj] = discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False)
                if staff_rol_obj:
                    cat_overwrites[staff_rol_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                categorie = await guild.create_category(cat_naam, overwrites=cat_overwrites)
            elif "ALGEMENE INFORMATIE" in cat_naam:
                categorie = await guild.create_category(cat_naam)
            else:
                cat_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                }
                if lid_rol_obj:
                    cat_overwrites[lid_rol_obj] = discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=True)
                if staff_rol_obj:
                    cat_overwrites[staff_rol_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                categorie = await guild.create_category(cat_naam, overwrites=cat_overwrites)

            for ch_tuple in kanalen:
                ch_naam = ch_tuple[0]
                is_staff_only = ch_tuple[2]
                is_verification = ch_tuple[3]
                is_premium_channel = ch_tuple[4]

                if is_verification:
                    ch_overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    }
                    if staff_rol_obj:
                        ch_overwrites[staff_rol_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    await guild.create_text_channel(ch_naam, category=categorie, overwrites=ch_overwrites)
                elif is_premium_channel:
                    ch_overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    }
                    if premium_klant_rol_obj:
                        ch_overwrites[premium_klant_rol_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
                    if staff_rol_obj:
                        ch_overwrites[staff_rol_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    await guild.create_text_channel(ch_naam, category=categorie, overwrites=ch_overwrites)
                elif "ALGEMENE INFORMATIE" in cat_naam:
                    ch_overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    }
                    if lid_rol_obj:
                        ch_overwrites[lid_rol_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
                    if not_verified_rol_obj:
                        ch_overwrites[not_verified_rol_obj] = discord.PermissionOverwrite(view_channel=False)
                    if staff_rol_obj:
                        ch_overwrites[staff_rol_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    await guild.create_text_channel(ch_naam, category=categorie, overwrites=ch_overwrites)
                elif is_staff_only and staff_rol_obj:
                    ch_overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        staff_rol_obj: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                    }
                    await guild.create_text_channel(ch_naam, category=categorie, overwrites=ch_overwrites)
                else:
                    await guild.create_text_channel(ch_naam, category=categorie)
        except Exception as e:
            print(f"Fout bij maken van kanaal/categorie: {e}")


# --------------------------------------------------------------------------
# Winkel & Klant Commands
# --------------------------------------------------------------------------
@tree.command(name="shop", description="Open de winkel en kies een bot")
async def shop_cmd(interaction: discord.Interaction):
    if not SHOP["producten"]:
        await interaction.response.send_message("De winkel is momenteel leeg.", ephemeral=True)
        return
    e = bots_embed("🛒 Bot Winkel")
    e.set_footer(text=f"{SERVERNAAM} • Selecteer hieronder een product.")
    await interaction.response.send_message(embed=e, view=BestelShopView(), ephemeral=True)


@tree.command(name="mijnbestellingen", description="Bekijk jouw actieve bestellingen")
async def mijnbestellingen_cmd(interaction: discord.Interaction):
    mijn = [b for b in SHOP["bestellingen"] if b["gebruiker_id"] == interaction.user.id]
    if not mijn:
        await interaction.response.send_message("Je hebt nog geen actieve bestellingen.", ephemeral=True)
        return
    e = embed("📦 Jouw Bestellingen")
    for b in mijn[-10:]:
        e.add_field(
            name=f"{STATUS_ICOON[b['status']]} Bestelling #{b['id']} — {b['product_naam']}",
            value=f"Prijs: {euro(b['prijs'])} • Status: {b['status']}",
            inline=False,
        )
    await interaction.response.send_message(embed=e, ephemeral=True)


@tree.command(name="review", description="Laat een review achter over je aankoop")
@app_commands.describe(sterren="Aantal sterren (1 t/m 5)", tekst="Jouw ervaring")
async def review_cmd(
    interaction: discord.Interaction,
    sterren: app_commands.Range[int, 1, 5],
    tekst: app_commands.Range[str, 5, 500],
):
    kandidaten = [
        b for b in SHOP["bestellingen"]
        if b["gebruiker_id"] == interaction.user.id and b["status"] == "afgerond" and not b.get("review")
    ]
    if not kandidaten:
        await interaction.response.send_message(
            "Je hebt geen afgeronde bestelling om te beoordelen (of je hebt al een review achtergelaten).", ephemeral=True
        )
        return
    kanaal = discord.utils.get(interaction.guild.text_channels, name="klanten-reviews")
    if kanaal is None:
        await interaction.response.send_message("Het kanaal #klanten-reviews kon niet worden gevonden.", ephemeral=True)
        return

    b = kandidaten[-1]
    e = discord.Embed(
        title="⭐" * sterren + "☆" * (5 - sterren) + f"  {b['product_naam']}",
        description=tekst,
        colour=0xFEE75C,
    )
    e.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    e.set_footer(text=SERVERNAAM)
    await kanaal.send(embed=e)
    b["review"] = True
    bewaar_shop()
    await interaction.response.send_message("Bedankt voor je review! 💙", ephemeral=True)


# --------------------------------------------------------------------------
# Staff Beheer Commands
# --------------------------------------------------------------------------
@tree.command(name="product_toevoegen", description="Voeg een bot toe aan de winkel (staff)")
@app_commands.describe(naam="Naam van de bot", omschrijving="Beschrijving", prijs="Prijs in euro")
async def product_toevoegen_cmd(interaction: discord.Interaction, naam: str, omschrijving: str, prijs: float):
    if not await staff_check(interaction):
        return
    if any(p["naam"].lower() == naam.lower() for p in SHOP["producten"]):
        await interaction.response.send_message("Er bestaat al een product met deze naam.", ephemeral=True)
        return
    p = {"id": SHOP["volgend_product"], "naam": naam, "omschrijving": omschrijving, "prijs": round(prijs, 2)}
    SHOP["volgend_product"] += 1
    SHOP["producten"].append(p)
    bewaar_shop()
    await interaction.response.send_message("✅ Product succesvol toegevoegd:", embed=product_embed(p), ephemeral=True)


@tree.command(name="product_bewerken", description="Bewerk een bestaand product (staff)")
@app_commands.describe(product="Selecteer product", nieuwe_naam="Nieuwe naam", omschrijving="Nieuwe omschrijving", prijs="Nieuwe prijs")
@app_commands.autocomplete(product=product_autocomplete)
async def product_bewerken_cmd(interaction: discord.Interaction, product: str, nieuwe_naam: str = None, omschrijving: str = None, prijs: float = None):
    if not await staff_check(interaction):
        return
    p = vind_product(product)
    if p is None:
        await interaction.response.send_message("Product niet gevonden.", ephemeral=True)
        return
    if nieuwe_naam:
        p["naam"] = nieuwe_naam
    if omschrijving:
        p["omschrijving"] = omschrijving
    if prijs is not None:
        p["prijs"] = round(prijs, 2)
    bewaar_shop()
    await interaction.response.send_message("✅ Product bijgewerkt:", embed=product_embed(p), ephemeral=True)


@tree.command(name="product_verwijderen", description="Verwijder een product uit de winkel (staff)")
@app_commands.describe(product="Selecteer product")
@app_commands.autocomplete(product=product_autocomplete)
async def product_verwijderen_cmd(interaction: discord.Interaction, product: str):
    if not await staff_check(interaction):
        return
    p = vind_product(product)
    if p is None:
        await interaction.response.send_message("Product niet gevonden.", ephemeral=True)
        return
    SHOP["producten"].remove(p)
    bewaar_shop()
    await interaction.response.send_message(f"🗑️ **{p['naam']}** is verwijderd uit de winkel.", ephemeral=True)


@tree.command(name="bestellingen", description="Bekijk alle open bestellingen (staff)")
async def bestellingen_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction):
        return
    open_b = [b for b in SHOP["bestellingen"] if b["status"] == "open"]
    if not open_b:
        await interaction.response.send_message("Er zijn geen open bestellingen.", ephemeral=True)
        return
    e = embed(f"🟡 Open Bestellingen ({len(open_b)})")
    for b in open_b[:25]:
        ticket = f"<#{b['ticket_kanaal_id']}>" if interaction.guild.get_channel(b["ticket_kanaal_id"]) else "gesloten"
        e.add_field(name=f"#{b['id']} — {b['product_naam']}", value=f"Klant: <@{b['gebruiker_id']}> • {euro(b['prijs'])} • Ticket: {ticket}", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)


@tree.command(name="afronden", description="Rond een bestelling af en ken automatisch de juiste klantrol toe (staff)")
@app_commands.describe(bestelling_id="Bestellingsnummer")
async def afronden_cmd(interaction: discord.Interaction, bestelling_id: int):
    if not await staff_check(interaction):
        return
    b = vind_bestelling(bestelling_id)
    if b is None or b["status"] != "open":
        await interaction.response.send_message("Bestelling niet gevonden of reeds afgehandeld.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    b["status"] = "afgerond"
    b["afgerond_door"] = interaction.user.id
    bewaar_shop()

    rol_melding = ""
    lid = guild.get_member(b["gebruiker_id"])
    
    if lid:
        is_premium = "premium" in b["product_naam"].lower()
        
        if is_premium:
            prem_rol = discord.utils.get(guild.roles, name=PREMIUM_KLANT_ROL)
            klant_rol = discord.utils.get(guild.roles, name=KLANT_ROL)
            try:
                if prem_rol:
                    await lid.add_roles(prem_rol)
                if klant_rol:
                    await lid.add_roles(klant_rol)
                rol_melding = f" De rollen **{PREMIUM_KLANT_ROL}** en **{KLANT_ROL}** zijn toegekend!"
            except Exception:
                pass
        else:
            klant_rol = discord.utils.get(guild.roles, name=KLANT_ROL)
            try:
                if klant_rol:
                    await lid.add_roles(klant_rol)
                rol_melding = f" De rol **{KLANT_ROL}** is toegekend."
            except Exception:
                pass

    ticket = guild.get_channel(b["ticket_kanaal_id"])
    if ticket:
        await ticket.send(f"✅ <@{b['gebruiker_id']}> jouw bestelling **#{b['id']} ({b['product_naam']})** is afgerond! Bedankt voor je aankoop.")
    await log_bestelling(guild, bestelling_embed(b, f"✅ Bestelling #{b['id']} afgerond"))
    await interaction.followup.send(f"✅ Bestelling #{b['id']} afgerond.{rol_melding}", ephemeral=True)


@tree.command(name="annuleren", description="Annuleer een open bestelling (staff/klant)")
@app_commands.describe(bestelling_id="Bestellingsnummer")
async def annuleren_cmd(interaction: discord.Interaction, bestelling_id: int):
    b = vind_bestelling(bestelling_id)
    if b is None:
        await interaction.response.send_message("Bestelling niet gevonden.", ephemeral=True)
        return
    if not (is_staff(interaction.user) or b["gebruiker_id"] == interaction.user.id):
        await interaction.response.send_message("Geen rechten om deze bestelling te annuleren.", ephemeral=True)
        return
    if b["status"] != "open":
        await interaction.response.send_message("Deze bestelling is al gesloten.", ephemeral=True)
        return
    b["status"] = "geannuleerd"
    bewaar_shop()
    await log_bestelling(interaction.guild, bestelling_embed(b, f"🔴 Bestelling #{b['id']} geannuleerd"))
    await interaction.response.send_message(f"🔴 Bestelling #{b['id']} is geannuleerd.", ephemeral=True)


@tree.command(name="blacklist", description="Voeg een gebruiker toe aan de verificatie-blacklist (staff)")
@app_commands.describe(user_id="Discord ID van de raider/alt")
async def blacklist_cmd(interaction: discord.Interaction, user_id: str):
    if not await staff_check(interaction):
        return
    try:
        uid = int(user_id)
    except ValueError:
        await interaction.response.send_message("Ongeldig ID opgegeven.", ephemeral=True)
        return

    if uid not in SHOP["blacklist"]:
        SHOP["blacklist"].append(uid)
        bewaar_shop()
        await interaction.response.send_message(f"✅ Gebruiker `{uid}` is toegevoegd aan de blacklist.", ephemeral=True)
    else:
        await interaction.response.send_message("Deze gebruiker staat al op de blacklist.", ephemeral=True)


@tree.command(name="verwijderblacklist", description="Verwijder een gebruiker van de verificatie-blacklist (staff)")
@app_commands.describe(user_id="Discord ID van de gebruiker die je wilt ontgrendelen")
async def verwijder_blacklist_cmd(interaction: discord.Interaction, user_id: str):
    if not await staff_check(interaction):
        return
    try:
        uid = int(user_id)
    except ValueError:
        await interaction.response.send_message("Ongeldig ID opgegeven. Zorg ervoor dat je alleen cijfers invult.", ephemeral=True)
        return

    if "blacklist" in SHOP and uid in SHOP["blacklist"]:
        SHOP["blacklist"].remove(uid)
        bewaar_shop()
        await interaction.response.send_message(f"✅ Gebruiker `{uid}` is succesvol verwijderd van de blacklist.", ephemeral=True)
        
        mod_logs = discord.utils.get(interaction.guild.text_channels, name="mod-logs")
        if mod_logs:
            await mod_logs.send(f"🔓 **Blacklist verwijdering:** Gebruiker `<@{uid}>` (`{uid}`) is door {interaction.user.mention} van de blacklist gehaald.")
    else:
        await interaction.response.send_message("❌ Deze gebruiker staat niet op de blacklist.", ephemeral=True)


@tree.command(name="kortingscode_maken", description="Maak een kortingscode aan (staff)")
@app_commands.describe(code="Code naam", procent="Korting in procenten")
async def kortingscode_maken_cmd(interaction: discord.Interaction, code: str, procent: int):
    if not await staff_check(interaction):
        return
    sleutel = code.strip().upper()
    SHOP["kortingscodes"][sleutel] = procent
    bewaar_shop()
    await interaction.response.send_message(f"✅ Kortingscode `{sleutel}` ({procent}%) is aangemaakt.", ephemeral=True)


@tree.command(name="kortingscode_verwijderen", description="Verwijder een kortingscode (staff)")
@app_commands.describe(code="Code naam")
async def kortingscode_verwijderen_cmd(interaction: discord.Interaction, code: str):
    if not await staff_check(interaction):
        return
    sleutel = code.strip().upper()
    if SHOP["kortingscodes"].pop(sleutel, None) is None:
        await interaction.response.send_message("Deze code bestaat niet.", ephemeral=True)
        return
    bewaar_shop()
    await interaction.response.send_message(f"🗑️ Kortingscode `{sleutel}` is verwijderd.", ephemeral=True)


@tree.command(name="kortingscodes", description="Toon actieve kortingscodes (staff)")
async def kortingscodes_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction):
        return
    if not SHOP["kortingscodes"]:
        await interaction.response.send_message("Er zijn geen actieve kortingscodes.", ephemeral=True)
        return
    regels = "\n".join(f"`{c}`: {p}% korting" for c, p in SHOP["kortingscodes"].items())
    await interaction.response.send_message(embed=embed("🏷️ Actieve Kortingscodes", regels), ephemeral=True)


@tree.command(name="shopstats", description="Toon omzet en shop statistieken (staff)")
async def shopstats_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction):
        return
    alle = SHOP["bestellingen"]
    afgerond = [b for b in alle if b["status"] == "afgerond"]
    tellingen = {}
    for b in afgerond:
        tellingen[b["product_naam"]] = tellingen.get(b["product_naam"], 0) + 1
    populair = max(tellingen, key=tellingen.get) if tellingen else "Nog geen verkopen"

    e = embed("📊 Shop Statistieken")
    e.add_field(name="Totale Omzet", value=euro(sum(b["prijs"] for b in afgerond)))
    e.add_field(name="Afgeronde Orders", value=str(len(afgerond)))
    e.add_field(name="Openstaande Orders", value=str(sum(b["status"] == "open" for b in alle)))
    e.add_field(name="Populairste Bot", value=populair, inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)


# Start de bot
client = FinnsBot()
client.run(TOKEN)
