import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Laad de .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID") or 1556668456315781321)

if not TOKEN:
    print("❌ CRITICHE FOUT: Geen DISCORD_TOKEN gevonden in het .env bestand!")
    exit(1)

# --------------------------------------------------------------------------
# Instellingen & Configuratie
# --------------------------------------------------------------------------
SERVERNAAM = "Finns Bots"
KLEUR = 0x5865F2
STAFF_ROL = "Staff"
LID_ROL_ID = 1557813756288045229  # Geverifieerde leden rol
KLANT_ROL = "Klant"
PREMIUM_KLANT_ROL = "💎 Premium Klant"
NOT_VERIFIED_ROL = "Not-Verified"
NOT_VERIFIED_ROL_ID = 1557808209924726889  # Gecorrigeerd rol-ID
TICKET_CATEGORIE = "🎫 ┃ BESTELLEN & SUPPORT"
VERIFICATIE_LOG_KANAAL_ID = 1557822081528369287

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
CONFIG_BESTAND = Path(__file__).with_name("bot_config.json")

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
# Config helper voor Joinlogs
# --------------------------------------------------------------------------
def laad_config():
    if CONFIG_BESTAND.exists():
        try:
            return json.loads(CONFIG_BESTAND.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"joinlogs_enabled": False, "joinlogs_channel_id": None}

def bewaar_config(conf):
    CONFIG_BESTAND.write_text(json.dumps(conf, indent=2), encoding="utf-8")

CONFIG = laad_config()


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
        "🔒 Server Verificatie",
        "Welkom! Om volledige toegang te krijgen tot de server, dien je jezelf te verifiëren.\n\n"
        "Klik op de knop hieronder om het verificatieproces te starten in je privéberichten (DM)."
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
                "`/joinlogs-setup`  stel het joinlogs kanaal in\n"
                "`/joinlogs-enable`  zet joinlogs aan\n"
                "`/joinlogs-disable`  zet joinlogs uit\n"
                "`/purge [aantal]`  verwijder snel berichten in een kanaal\n"
                "`/bestellingen`  openstaande bestellingen inzien\n"
                "`/afronden`  bestelling afronden & klant-rol toekennen\n"
                "`/annuleren`  bestelling annuleren\n"
                "`/serverwipe`  wist alle berichten, behoudt kanalen & reset rollen\n"
                "`/product_toevoegen`, `/product_bewerken`, `/product_verwijderen`\n"
                "`/blacklist`, `/verwijderblacklist`\n"
                "`/kortingscode_maken`, `/kortingscodes`, `/kortingscode_verwijderen`\n"
                "`/shopstats`  gedetailleerde omzet en statistieken\n"
                "`/maakserver`, `/shutdown`, `/startup`, `/verificatie-setup`, `/setup_embeds`"
            ),
            inline=False,
        )
    return e


# --------------------------------------------------------------------------
# Interactieve Moderatie Knoppen voor Verificatie Logs (In Server)
# --------------------------------------------------------------------------
class ModeratieActieKnop(discord.ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id

    @discord.ui.button(label="Ban user", emoji="🔨", style=discord.ButtonStyle.danger, custom_id="ban_user_btn")
    async def ban_actie(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("Geen rechten om dit uit te voeren.", ephemeral=True)
            return
        try:
            guild = interaction.guild
            member = guild.get_member(self.target_user_id) or await guild.fetch_member(self.target_user_id)
            await guild.ban(member, reason=f"Gebanned via verificatiepaneel door {interaction.user}")
            await interaction.response.send_message(f"🔨 Gebruiker {member.mention} is succesvol gebanned.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Kan gebruiker niet bannen: {e}", ephemeral=True)

    @discord.ui.button(label="Kick user", emoji="🛡️", style=discord.ButtonStyle.secondary, custom_id="kick_user_btn")
    async def kick_actie(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("Geen rechten om dit uit te voeren.", ephemeral=True)
            return
        try:
            guild = interaction.guild
            member = guild.get_member(self.target_user_id) or await guild.fetch_member(self.target_user_id)
            await guild.kick(member, reason=f"Gekicked via verificatiepaneel door {interaction.user}")
            await interaction.response.send_message(f"🛡️ Gebruiker {member.mention} is succesvol gekicked.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Kan gebruiker niet kicken: {e}", ephemeral=True)


# --------------------------------------------------------------------------
# DM Verificatie Knoppen View (Vinkje / Kruisje in DM)
# --------------------------------------------------------------------------
class DMVerificatieKnopView(discord.ui.View):
    def __init__(self, guild: discord.Guild, member_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.member_id = member_id

    @discord.ui.button(label="Verifiëren", emoji="✅", style=discord.ButtonStyle.success)
    async def bevestig(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.member_id:
            await interaction.response.send_message("Dit is niet jouw verificatiebericht.", ephemeral=True)
            return

        try:
            guild_member = await self.guild.fetch_member(self.member_id)
            nieuwe_rol = self.guild.get_role(LID_ROL_ID)

            if not nieuwe_rol:
                await interaction.response.edit_message(content="❌ Fout: De geverifieerde rol kan niet worden gevonden in de server.", view=None)
                return

            # Verwijder oude rollen behalve @everyone en eventuele bot-rollen
            te_verwijderen = [r for r in guild_member.roles if r != self.guild.default_role and not r.managed]
            if te_verwijderen:
                try:
                    await guild_member.remove_roles(*te_verwijderen, reason="Server Verificatie: oude rollen verwijderd")
                except Exception as ex:
                    print(f"Kon oude rollen niet verwijderen: {ex}")

            # Voeg de geverifieerde rol toe
            try:
                await guild_member.add_roles(nieuwe_rol, reason="Server Verificatie voltooid")
            except Exception as ex:
                print(f"Kon nieuwe rol niet toekennen: {ex}")
                await interaction.response.edit_message(content="❌ Kan de rol niet toekennen. Controleer of de bot-rol **boven** de geverifieerde rol staat in de serverinstellingen!", view=None)
                return

            await interaction.response.edit_message(content="✅ Je bent succesvol geverifieerd! Je hebt nu toegang tot de server.", view=None)

            # Stuur log naar logkanaal
            log_kanaal = self.guild.get_channel(VERIFICATIE_LOG_KANAAL_ID)
            if log_kanaal:
                tijdzone = "UTC / Systeem lokaal"
                e = embed(
                    "🛡️ Nieuwe Verificatie Details",
                    f"**Naam:** {guild_member.name} (`{guild_member.display_name}`)\n"
                    f"**Discord ID:** `{guild_member.id}`\n"
                    f"**Account Aangemaakt:** {discord.utils.format_dt(guild_member.created_at, 'R')}\n"
                    f"**Tijdzone:** {tijdzone}"
                )
                if guild_member.display_avatar:
                    e.set_thumbnail(url=guild_member.display_avatar.url)
                
                await log_kanaal.send(embed=e, view=ModeratieActieKnop(guild_member.id))

        except Exception as e:
            print(f"Fout bij verifiëren via DM: {e}")
            await interaction.response.edit_message(content=f"❌ Er is een onverwachte fout opgetreden: {e}", view=None)

    @discord.ui.button(label="Annuleren", emoji="❌", style=discord.ButtonStyle.danger)
    async def annuleer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.member_id:
            await interaction.response.send_message("Dit is niet jouw verificatiebericht.", ephemeral=True)
            return
        await interaction.response.edit_message(content="❌ Verificatie geannuleerd.", view=None)


# --------------------------------------------------------------------------
# Directe Verificatie Knop in Server
# --------------------------------------------------------------------------
class VerifieerDiscordKnop(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verifiëren", emoji="✅", style=discord.ButtonStyle.success, custom_id="discord_direct_verifieer_knop")
    async def verifieer(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        if member.id in SHOP.get("blacklist", []):
            await interaction.response.send_message("❌ Je kunt niet verifiëren omdat je account op de blacklist staat.", ephemeral=True)
            return

        try:
            dm_channel = await member.create_dm()
            e = embed(
                "🔒 Server Verificatie",
                f"Welkom bij **{SERVERNAAM}**!\n\n"
                "Klik hieronder op **✅ Verifiëren** om je rollen te ontvangen, of op **❌ Annuleren**."
            )
            await dm_channel.send(embed=e, view=DMVerificatieKnopView(guild, member.id))
            await interaction.response.send_message("📬 Er is een verificatiebericht naar je privéberichten (DM) gestuurd!", ephemeral=True)
        except Exception:
            await interaction.response.send_message(
                "⚠️ **Kon geen DM sturen!** Je privéberichten staan uit. Klik op de knop hieronder om direct in dit kanaal te verifiëren.",
                view=FallbackKanaalVerificatieView(guild),
                ephemeral=True
            )


class FallbackKanaalVerificatieView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=60)
        self.guild = guild

    @discord.ui.button(label="Verifieer direct hier", emoji="✅", style=discord.ButtonStyle.success)
    async def direct_verifieer(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        try:
            guild_member = await self.guild.fetch_member(member.id)
            nieuwe_rol = self.guild.get_role(LID_ROL_ID)

            te_verwijderen = [r for r in guild_member.roles if r != self.guild.default_role and not r.managed]
            if te_verwijderen:
                try:
                    await guild_member.remove_roles(*te_verwijderen)
                except Exception:
                    pass

            if nieuwe_rol:
                await guild_member.add_roles(nieuwe_rol)

            await interaction.response.edit_message(content="✅ Je bent succesvol geverifieerd via het kanaal!", view=None)

            log_kanaal = self.guild.get_channel(VERIFICATIE_LOG_KANAAL_ID)
            if log_kanaal:
                tijdzone = "UTC / Systeem lokaal"
                e = embed(
                    "🛡️ Nieuwe Verificatie Details (Via Kanaal Fallback)",
                    f"**Naam:** {guild_member.name} (`{guild_member.display_name}`)\n"
                    f"**Discord ID:** `{guild_member.id}`\n"
                    f"**Account Aangemaakt:** {discord.utils.format_dt(guild_member.created_at, 'R')}\n"
                    f"**Tijdzone:** {tijdzone}"
                )
                if guild_member.display_avatar:
                    e.set_thumbnail(url=guild_member.display_avatar.url)
                
                await log_kanaal.send(embed=e, view=ModeratieActieKnop(guild_member.id))
        except Exception as e:
            await interaction.response.edit_message(content=f"❌ Fout bij verifiëren: {e}", view=None)


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
# Bot Hoofdklasse & Veilige Sync
# --------------------------------------------------------------------------
class FinnsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix="m?", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifieerDiscordKnop())
        self.add_view(TicketKnop())
        self.add_view(SluitKnop())
        
        try:
            if GUILD_ID and GUILD_ID != 0:
                guild = discord.Object(id=GUILD_ID)
                self.tree.clear_commands(guild=guild)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            print("✅ Slash commando's succesvol gesynchroniseerd voor de server.")
        except Exception as e:
            print(f"⚠️ Waarschuwing bij synchroniseren: {e}")

    async def on_ready(self):
        await self.change_presence(activity=discord.Game(name="Bots verkopen | /help"))
        print(f"🤖 Ingelogd als {self.user} (ID: {self.user.id})")

    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        not_verified_rol = guild.get_role(NOT_VERIFIED_ROL_ID) if NOT_VERIFIED_ROL_ID else discord.utils.get(guild.roles, name=NOT_VERIFIED_ROL)
        if not_verified_rol:
            try:
                await member.add_roles(not_verified_rol)
            except Exception:
                pass

        if CONFIG.get("joinlogs_enabled") and CONFIG.get("joinlogs_channel_id"):
            log_ch = guild.get_channel(CONFIG["joinlogs_channel_id"])
            if log_ch:
                e = embed("📥 Lid Getreden", f"{member.mention} (`{member.name}`) is de server binnengekomen.")
                e.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
                await log_ch.send(embed=e)

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
                    except Exception:
                        pass

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
            except Exception:
                pass

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
# Alle Commando's
# --------------------------------------------------------------------------
@tree.command(name="help", description="Toon alle beschikbare commando's")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=help_embed(is_staff(interaction.user)), ephemeral=True)


@tree.command(name="bots", description="Bekijk al onze beschikbare bots")
async def bots_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=bots_embed(), ephemeral=True)


@tree.command(name="prijzen", description="Bekijk de prijzenlijst")
async def prijzen_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=prijzen_embed(), ephemeral=True)


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
    await interaction.response.send_message(embed=e, ephemeral=True)


@tree.command(name="ping", description="Test de reactiesnelheid van de bot")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! Latency is {round(client.latency * 1000)} ms", ephemeral=True)


@tree.command(name="verificatie-setup", description="Plaats het verificatiepaneel in het kanaal (Alleen Eigenaar)")
async def verificatie_setup_cmd(interaction: discord.Interaction):
    if interaction.user != interaction.guild.owner and not is_staff(interaction.user):
        await interaction.response.send_message("❌ Geen rechten om dit uit te voeren.", ephemeral=True)
        return

    await interaction.channel.send(embed=verificatie_embed(), view=VerifieerDiscordKnop())
    await interaction.response.send_message("✅ Verificatiepaneel succesvol geplaatst!", ephemeral=True)


# --- Purge Commando ---
@tree.command(name="purge", description="Verwijder een aantal berichten in dit kanaal (Staff)")
@app_commands.describe(aantal="Het aantal berichten dat je wilt verwijderen")
async def purge_cmd(interaction: discord.Interaction, aantal: int):
    if not await staff_check(interaction):
        return
    
    if aantal <= 0:
        await interaction.response.send_message("❌ Geef een getal op dat groter is dan 0.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        verwijderd = await interaction.channel.purge(limit=aantal)
        await interaction.followup.send(f"🧹 Er zijn succesvol **{len(verwijderd)}** berichten verwijderd.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Er is een fout opgetreden bij het purgen van berichten: {e}", ephemeral=True)


# --- Joinlogs Commando's ---
@tree.command(name="joinlogs-setup", description="Stel het kanaal in waar joinlogs naartoe gestuurd moeten worden (Staff)")
@app_commands.describe(kanaal="Het tekstkanaal voor joinlogs")
async def joinlogs_setup_cmd(interaction: discord.Interaction, kanaal: discord.TextChannel):
    if not await staff_check(interaction):
        return
    CONFIG["joinlogs_channel_id"] = kanaal.id
    bewaar_config(CONFIG)
    await interaction.response.send_message(f"✅ Joinlogs kanaal is ingesteld op {kanaal.mention}.", ephemeral=True)


@tree.command(name="joinlogs-enable", description="Zet joinlogs aan (Staff)")
async def joinlogs_enable_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction):
        return
    CONFIG["joinlogs_enabled"] = True
    bewaar_config(CONFIG)
    await interaction.response.send_message("✅ Joinlogs zijn **ingeschakeld**.", ephemeral=True)


@tree.command(name="joinlogs-disable", description="Zet joinlogs uit (Staff)")
async def joinlogs_disable_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction):
        return
    CONFIG["joinlogs_enabled"] = False
    bewaar_config(CONFIG)
    await interaction.response.send_message("❌ Joinlogs zijn **uitgeschakeld**.", ephemeral=True)


@tree.command(name="setup_embeds", description="Plaats welkomst- en infobereichten in de kanalen (admin)")
@app_commands.default_permissions(administrator=True)
async def setup_embeds_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    g = interaction.guild

    doelen = {
        "verificatie": (verificatie_embed(), VerifieerDiscordKnop()),
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
        try:
            if view:
                await kanaal.send(embed=e, view=view)
            else:
                await kanaal.send(embed=e)
            geplaatst.append(f"#{naam}")
        except Exception:
            pass

    tekst = "Berichten succesvol geplaatst in: " + ", ".join(geplaatst) if geplaatst else "Geen berichten geplaatst."
    if ontbreekt:
        tekst += "\nNiet gevonden kanalen: " + ", ".join(f"#{n}" for n in ontbreekt)
    await interaction.followup.send(tekst, ephemeral=True)


@tree.command(name="shutdown", description="Zet de server hermetisch op slot (Admin)")
async def shutdown_cmd(interaction: discord.Interaction):
    if not any(rol.id == SHUTDOWN_ROL_ID for rol in interaction.user.roles):
        await interaction.response.send_message("Geen toestemming.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    for category in guild.categories:
        try:
            await category.edit(sync_permissions=False)
            await category.set_permissions(guild.default_role, read_messages=False, view_channel=False, connect=False)
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
        except Exception:
            pass

    await interaction.followup.send("🚨 **Server Lockdown is geactiveerd!**", ephemeral=True)


@tree.command(name="startup", description="Heft de shutdown op (Admin)")
async def startup_cmd(interaction: discord.Interaction):
    if not any(rol.id == SHUTDOWN_ROL_ID for rol in interaction.user.roles):
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


@tree.command(name="serverwipe", description="Wist alle berichten en zet rollen terug (Admin)")
async def serverwipe_cmd(interaction: discord.Interaction):
    if not any(rol.id == SHUTDOWN_ROL_ID for rol in interaction.user.roles):
        await interaction.response.send_message("Geen toestemming.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    not_verified_rol = guild.get_role(NOT_VERIFIED_ROL_ID) if NOT_VERIFIED_ROL_ID else discord.utils.get(guild.roles, name=NOT_VERIFIED_ROL)

    for member in guild.members:
        if member.bot or member.guild_permissions.administrator:
            continue
        try:
            te_verwijderen = [r for r in member.roles if r != guild.default_role]
            if te_verwijderen:
                await member.remove_roles(*te_verwijderen)
            if not_verified_rol:
                await member.add_roles(not_verified_rol)
        except Exception:
            pass

    for channel in list(guild.text_channels):
        try:
            category = channel.category
            overwrites = channel.overwrites
            name = channel.name
            topic = channel.topic
            await channel.delete()
            await guild.create_text_channel(name, category=category, overwrites=overwrites, topic=topic)
        except Exception:
            pass

    await interaction.followup.send("💥 **Server Wipe voltooid!**", ephemeral=True)


@tree.command(name="maakserver", description="Stelt de complete serverstructuur in (Admin)")
async def maakserver_cmd(interaction: discord.Interaction):
    if not any(rol.id == SHUTDOWN_ROL_ID for rol in interaction.user.roles):
        await interaction.response.send_message("Geen toestemming.", ephemeral=True)
        return

    await interaction.response.send_message("⚙️ Bezig met het instellen van de serverstructuur...", ephemeral=True)
    guild = interaction.guild

    for channel in list(guild.channels):
        try:
            await channel.delete()
        except Exception:
            pass

    await guild.create_category("🎫 ┃ BESTELLEN & SUPPORT")
    await guild.create_text_channel("koop-een-bot", category=discord.utils.get(guild.categories, name="🎫 ┃ BESTELLEN & SUPPORT"))
    await interaction.followup.send("✅ Serverstructuur succesvol aangemaakt!", ephemeral=True)


@tree.command(name="shop", description="Open de winkel en kies een bot")
async def shop_cmd(interaction: discord.Interaction):
    if not SHOP["producten"]:
        await interaction.response.send_message("De winkel is momenteel leeg.", ephemeral=True)
        return
    e = bots_embed("🛒 Bot Winkel")
    await interaction.response.send_message(embed=e, view=BestelShopView(), ephemeral=True)


@tree.command(name="mijnbestellingen", description="Bekijk jouw actieve bestellingen")
async def mijnbestellingen_cmd(interaction: discord.Interaction):
    mijn = [b for b in SHOP["bestellingen"] if b["gebruiker_id"] == interaction.user.id]
    if not mijn:
        await interaction.response.send_message("Je hebt nog geen actieve bestellingen.", ephemeral=True)
        return
    e = embed("📦 Jouw Bestellingen")
    for b in mijn[-10:]:
        e.add_field(name=f"Bestelling #{b['id']} — {b['product_naam']}", value=f"Status: {b['status']}", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)


@tree.command(name="review", description="Laat een review achter over je aankoop")
async def review_cmd(interaction: discord.Interaction, sterren: app_commands.Range[int, 1, 5], tekst: str):
    await interaction.response.send_message("Bedankt voor je review! 💙", ephemeral=True)


@tree.command(name="bestellingen", description="Bekijk open bestellingen (staff)")
async def bestellingen_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction):
        return
    open_b = [b for b in SHOP["bestellingen"] if b["status"] == "open"]
    if not open_b:
        await interaction.response.send_message("Geen open bestellingen.", ephemeral=True)
        return
    e = embed(f"🟡 Open Bestellingen ({len(open_b)})")
    for b in open_b[:25]:
        e.add_field(name=f"#{b['id']} — {b['product_naam']}", value=f"Klant: <@{b['gebruiker_id']}>", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)


@tree.command(name="afronden", description="Rond een bestelling af (staff)")
async def afronden_cmd(interaction: discord.Interaction, bestelling_id: int):
    if not await staff_check(interaction):
        return
    b = vind_bestelling(bestelling_id)
    if not b:
        await interaction.response.send_message("Bestelling niet gevonden.", ephemeral=True)
        return
    b["status"] = "afgerond"
    bewaar_shop()
    await interaction.response.send_message(f"✅ Bestelling #{bestelling_id} afgerond.", ephemeral=True)


@tree.command(name="annuleren", description="Annuleer een bestelling")
async def annuleren_cmd(interaction: discord.Interaction, bestelling_id: int):
    b = vind_bestelling(bestelling_id)
    if not b:
        await interaction.response.send_message("Bestelling niet gevonden.", ephemeral=True)
        return
    b["status"] = "geannuleerd"
    bewaar_shop()
    await interaction.response.send_message(f"🔴 Bestelling #{bestelling_id} geannuleerd.", ephemeral=True)


@tree.command(name="blacklist", description="Zet gebruiker op blacklist (staff)")
async def blacklist_cmd(interaction: discord.Interaction, user_id: str):
    if not await staff_check(interaction):
        return
    uid = int(user_id)
    if uid not in SHOP["blacklist"]:
        SHOP["blacklist"].append(uid)
        bewaar_shop()
    await interaction.response.send_message(f"✅ Gebruiker `{uid}` op blacklist gezet.", ephemeral=True)


@tree.command(name="verwijderblacklist", description="Haal gebruiker van blacklist (staff)")
async def verwijder_blacklist_cmd(interaction: discord.Interaction, user_id: str):
    if not await staff_check(interaction):
        return
    uid = int(user_id)
    if uid in SHOP["blacklist"]:
        SHOP["blacklist"].remove(uid)
        bewaar_shop()
    await interaction.response.send_message(f"✅ Gebruiker `{uid}` van blacklist gehaald.", ephemeral=True)


# Start de bot
client.run(TOKEN)