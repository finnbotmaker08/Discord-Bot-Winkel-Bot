import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

# Eigen veilige .env parser
env_path = Path(__file__).with_name(".env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            parts = line.split("=", 1)
            key = parts[0].strip()
            val = parts[1].strip().split(" #")[0].split("#")[0].strip()
            if key:
                os.environ[key] = val
        elif not os.getenv("DISCORD_TOKEN"):
            os.environ["DISCORD_TOKEN"] = line

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("Geen DISCORD_TOKEN gevonden in je .env bestand!")

# ==========================================
# CONFIGURATIE & ID'S
# ==========================================
GUILD_ID = int(os.getenv("GUILD_ID", 1556668456315781321))
AUTOMATIC_JOIN_ROLE_ID = 1557813756288045229
VERIFIED_ROLE_ID = 1557808209924726889
UNVERIFIED_ROLE_ID = 1557813756288045229
KLANT_ROL_ID = 1556570231105781833
VERIFY_LOG_CHANNEL_ID = 1558408492887572530
WEEK_OVERZICHT_KANAAL_ID = 1558414858108534795
BESTELLINGEN_LOG_KANAAL_ID = 1557822081528369287

KANAAL_REGELS_ID = 1557822036154384457
KANAAL_WELKOM_ID = 1558409267021742180
KANAAL_SUPPORT_ID = 1557822060967886999
KANAAL_PRIJZEN_ID = 1557822048279994458
KANAAL_BESTELLEN_ID = 1557822059646554194
KANAAL_VERIFICATIE_ID = 1557822033545527493
KANAAL_REVIEWS_ID = 1558517860513349702

SERVERNAAM = "Finns Bots"
KLEUR = 0x5865F2
STAFF_ROL = "Staff"
LID_ROL = "Lid"
TICKET_CATEGORIE = "🎫 TICKETS"

MEDEDELING_KANAAL_ID = 1556575385284648980
SHUTDOWN_ROL_ID = 1556578093081305159

STATE_BESTAND = Path(__file__).with_name("shutdown_state.json")
SHOP_BESTAND = Path(__file__).with_name("shop_data.json")
STATS_BESTAND = Path(__file__).with_name("weekly_stats.json")

BOTS = [
    {
        "naam": "🛡️ Security Bot",
        "omschrijving": "Automoderatie, kick, ban, mute, warn, clear, slowmode, lockdown, unlock, suggestie.",
        "prijs": 7.50,
    },
    {
        "naam": "🤖 Normale Bot",
        "omschrijving": "Een bot met 10 custom commands en installatie tutorial.",
        "prijs": 10.00,
    },
    {
        "naam": "⭐ Premium Bot",
        "omschrijving": "15 custom commands, Security Bot inbegrepen, 24/7 hosting tutorial.",
        "prijs": 15.00,
    },
]

REGELS = [
    "Wees respectvol tegen iedereen.",
    "Geen spam, reclame of ongepaste inhoud.",
    "Bestel en betaal alleen via een ticket in #bestellen.",
    "Volg de aanwijzingen van het staffteam op.",
    "Gebruik de kanalen waarvoor ze bedoeld zijn.",
]

# ==========================================
# STATISTIEKEN INLADEN / BEWAREN
# ==========================================
def laad_stats():
    if STATS_BESTAND.exists():
        return json.loads(STATS_BESTAND.read_text(encoding="utf-8"))
    return {"joins": 0, "verificaties": 0, "nieuwe_bestellingen": 0, "afgeronde_bestellingen": 0}

def bewaar_stats(stats):
    STATS_BESTAND.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

WEEK_STATS = laad_stats()

# ==========================================
# HELPER FUNCTIES & EMBEDS
# ==========================================
STATUS_ICOON = {"open": "🟡", "afgerond": "🟢", "geannuleerd": "🔴"}

def embed(titel, beschrijving=None):
    e = discord.Embed(title=titel, description=beschrijving, colour=KLEUR)
    e.set_footer(text=SERVERNAAM)
    return e

def euro(bedrag):
    tekst = f"{bedrag:,.2f}"
    return "€" + tekst.replace(",", "_").replace(".", ",").replace("_", ".")

def laad_shop():
    if SHOP_BESTAND.exists():
        return json.loads(SHOP_BESTAND.read_text(encoding="utf-8"))
    return {
        "producten": [
            {"id": i, "naam": b["naam"], "omschrijving": b["omschrijving"], "prijs": b["prijs"]}
            for i, b in enumerate(BOTS, 1)
        ],
        "bestellingen": [],
        "kortingscodes": {},
        "volgend_product": len(BOTS) + 1,
        "volgende_bestelling": 1,
    }

def bewaar_shop():
    SHOP_BESTAND.write_text(json.dumps(SHOP, ensure_ascii=False, indent=2), encoding="utf-8")

_eerste_keer = not SHOP_BESTAND.exists()
SHOP = laad_shop()
if _eerste_keer:
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
    await interaction.response.send_message("Alleen staff kan dit.", ephemeral=True)
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
    
    WEEK_STATS["nieuwe_bestellingen"] += 1
    bewaar_stats(WEEK_STATS)
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
    if b['korting_procent']:
        e.add_field(name="Originele prijs", value=euro(b['originele_prijs']), inline=True)
        e.add_field(name="Kortingscode", value=f"`{b['korting_code']}` ({b['korting_procent']}% korting)", inline=True)
        e.add_field(name="Gecorrigeerde prijs", value=f"**{euro(b['prijs'])}**", inline=False)
    else:
        e.add_field(name="Prijs", value=f"**{euro(b['prijs'])}**", inline=False)
    e.add_field(name="Status", value=f"{STATUS_ICOON[b['status']]} {b['status']}", inline=False)
    e.set_footer(text=SERVERNAAM)
    return e

async def log_bestelling(guild, e):
    kanaal = guild.get_channel(BESTELLINGEN_LOG_KANAAL_ID)
    if kanaal is None:
        kanaal = discord.utils.get(guild.text_channels, name="bestellingen-log")
    if kanaal:
        await kanaal.send(embed=e)

def bots_embed(titel="🤖 Onze bots"):
    if not SHOP["producten"]:
        return embed(titel, "Er zijn nog geen producten. Kom snel terug!")
    e = embed(titel, "Dit is wat we nu verkopen:")
    for p in SHOP["producten"]:
        e.add_field(name=f"{p['naam']}  -  {euro(p['prijs'])}", value=p["omschrijving"], inline=False)
    return e

def prijzen_embed():
    e = discord.Embed(
        title="💶 Prijzenlijst",
        description="Transparante prijzen voor al onze diensten en bots:",
        colour=KLEUR
    )
    e.add_field(
        name="Security Bot\n€7,50",
        value=(
            "Automoderatie, kick, ban, mute, warn, clear, slowmode, lockdown, unlock, suggestie. "
            "+ Een tutorial hoe je alles moet downloaden en installeren zit erbij."
        ),
        inline=False
    )
    e.add_field(
        name="Normale Bot\n€10,00",
        value=(
            "Een bot met 10 custom commands. Een tutorial hoe je alles moet downloaden en "
            "installeren zit erbij."
        ),
        inline=False
    )
    e.add_field(
        name="Premium Bot\n€15,00",
        value=(
            "Premium bot. Je kan 15 custom commands kiezen, Security Bot zit erbij. "
            "Tutorial hoe je alles moet downloaden, installeren en 24/7 hosten."
        ),
        inline=False
    )
    e.set_footer(text=SERVERNAAM)
    return e

def welkom_embed():
    return embed(
        f"Welkom bij {SERVERNAAM}! 🤖",
        "Hier vind je custom Discord-bots voor jouw server.\n\n"
        "📦 Bekijk onze bots in **#bot-overzicht**\n"
        "💶 De prijzen staan in **#prijzen**\n"
        "🎫 Interesse? Open een ticket in **#bestellen**\n"
        "❓ Vragen? Stel ze in **#vragenensupport**",
    )

def regels_embed():
    tekst = "\n".join(f"**{i}.** {regel}" for i, regel in enumerate(REGELS, 1))
    return embed("📜 Serverregels", tekst)

def support_embed():
    return embed(
        "❓ Vragen & Support",
        "Heb je een vraag over onze bots of services? "
        "Open gerust een ticket via **#bestellen** of stel je vraag hier aan het team!"
    )

def help_embed(staff=False):
    e = embed(
        "📖 Commands",
        "`/shop`  open de winkel en kies een product\n"
        "`/bots`  de bots die we verkopen\n"
        "`/prijzen`  de prijslijst\n"
        "`/bestellen`  bestel direct een product (met optionele kortingscode)\n"
        "`/kortingscodegebruik`  controleer of een kortingscode geldig is\n"
        "`/mijnbestellingen`  je bestelgeschiedenis\n"
        "`/review`  laat een review achter\n"
        "`/serverinfo`  info over de server\n"
        "`/ping`  snelheidstest",
    )
    if staff:
        e.add_field(
            name="🔒 Staff",
            value=(
                "`/berichtbot`  stuur een bericht (met optionele afbeelding) als bot\n"
                "`/bestellingen`  open bestellingen\n"
                "`/afronden`  bestelling afronden\n"
                "`/annuleren`  bestelling annuleren\n"
                "`/product_toevoegen`, `/product_bewerken`, `/product_verwijderen`\n"
                "`/kortingscode_maken`, `/kortingscode_verwijderen`, `/kortingscodes`\n"
                "`/shopstats`  omzet en populairste product\n"
                "`/ban`, `/kick`, `/clear`, `/purge`  moderatie commando's"
            ),
            inline=False,
        )
    return e

# ==========================================
# INTERACTIEVE VIEWS & BUTTONS
# ==========================================
class LogModeratieView(ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id

    @ui.button(label="Ban user", emoji="🔨", style=discord.ButtonStyle.danger, custom_id="log_ban_user_btn")
    async def ban_user(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("Alleen staff kan dit doen.", ephemeral=True)
            return
        
        guild = interaction.guild
        member = guild.get_member(self.target_user_id)
        target_name = member.name if member else f"ID: {self.target_user_id}"

        try:
            await guild.ban(discord.Object(id=self.target_user_id), reason=f"Gebanned via logknoppen door {interaction.user}")
            await interaction.response.send_message(f"🔨 Gebruiker `{target_name}` is succesvol gebanned.", ephemeral=True)
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
        except Exception as e:
            await interaction.response.send_message(f"Kon gebruiker niet bannen: {e}", ephemeral=True)

    @ui.button(label="Kick user", emoji="🛡️", style=discord.ButtonStyle.secondary, custom_id="log_kick_user_btn")
    async def kick_user(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("Alleen staff kan dit doen.", ephemeral=True)
            return
        
        guild = interaction.guild
        member = guild.get_member(self.target_user_id)
        if not member:
            await interaction.response.send_message("Kan de gebruiker niet vinden in de server (misschien al weg).", ephemeral=True)
            return

        target_name = member.name
        try:
            await member.kick(reason=f"Gekicked via logknoppen door {interaction.user}")
            await interaction.response.send_message(f"🛡️ Gebruiker `{target_name}` is succesvol gekicked.", ephemeral=True)
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
        except Exception as e:
            await interaction.response.send_message(f"Kon gebruiker niet kicken: {e}", ephemeral=True)

class VerificationModal(ui.Modal, title="Server Verificatie"):
    antwoord = ui.TextInput(
        label="Typ hieronder het woord: VERIFIED",
        placeholder="Typ hier...",
        required=True,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        if self.antwoord.value.strip().upper() == "VERIFIED":
            guild = interaction.guild
            member = interaction.user
            verified_role = guild.get_role(VERIFIED_ROLE_ID)
            unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
            
            try:
                if verified_role:
                    await member.add_roles(verified_role)
                if unverified_role and unverified_role in member.roles:
                    await member.remove_roles(unverified_role)
                
                await interaction.response.send_message("Je bent succesvol geverifieerd!", ephemeral=True)
                
                WEEK_STATS["verificaties"] += 1
                bewaar_stats(WEEK_STATS)

                log_channel = guild.get_channel(VERIFY_LOG_CHANNEL_ID)
                if log_channel:
                    discord_join = discord.utils.format_dt(member.created_at, "R")
                    server_join = discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Onbekend"
                    
                    e = discord.Embed(
                        title="✅ Nieuwe Verificatie",
                        description=f"{member.mention} heeft zich succesvol geverifieerd.",
                        color=discord.Color.green()
                    )
                    if member.display_avatar:
                        e.set_thumbnail(url=member.display_avatar.url)
                    
                    e.add_field(name="Naam", value=f"{member.name} ({member.display_name})", inline=True)
                    e.add_field(name="Discord ID", value=str(member.id), inline=True)
                    e.add_field(name="Account aangemaakt", value=discord_join, inline=True)
                    e.add_field(name="Server gejoined", value=server_join, inline=True)
                    e.set_footer(text=SERVERNAAM)
                    
                    await log_channel.send(embed=e, view=LogModeratieView(member.id))
            except discord.Forbidden:
                await interaction.response.send_message("❌ De bot mist permissies!", ephemeral=True)
            except Exception as err:
                await interaction.response.send_message(f"Fout bij toewijzen van rollen: {err}", ephemeral=True)
        else:
            await interaction.response.send_message("Onjuist antwoord! Probeer het opnieuw.", ephemeral=True)

class VerificationView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Verifieer jezelf", style=discord.ButtonStyle.green, custom_id="verify_button_persistent")
    async def verify_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VerificationModal())

async def maak_ticket(interaction: discord.Interaction, product=None, code=None):
    guild = interaction.guild
    user = interaction.user

    for ch in guild.text_channels:
        if ch.topic == f"ticket:{user.id}":
            await interaction.response.send_message(f"Je hebt al een open ticket: {ch.mention}", ephemeral=True)
            return

    procent, gebruikte_code = 0, None
    if code:
        sleutel = code.strip().upper()
        if sleutel not in SHOP["kortingscodes"]:
            await interaction.response.send_message("❌ Die kortingscode is ongeldig.", ephemeral=True)
            return
        procent, gebruikte_code = SHOP["kortingscodes"][sleutel], sleutel

    staff = discord.utils.get(guild.roles, name=STAFF_ROL)
    toegang = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, read_message_history=True, attach_files=True
    )

    categorie = discord.utils.get(guild.categories, name=TICKET_CATEGORIE)
    if categorie is None:
        cat_overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        if staff:
            cat_overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
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
        
        if gebruikte_code:
            korting_tekst = (
                f"\n🎉 **Kortingscode geactiveerd:** `{gebruikte_code}`\n"
                f"• **Originele prijs:** ~~{euro(b['originele_prijs'])}~~\n"
                f"• **Korting:** {procent}%\n"
                f"• **Gecorrigeerde prijs:** **{euro(b['prijs'])}**\n"
            )
        else:
            korting_tekst = ""

        e.description = (
            f"Hoi {user.mention}! Bedankt voor je bestelling.{korting_tekst}\n"
            "Een stafflid stuurt je zo de betaalinstructies. "
            f"*Staff: gebruik `/afronden {b['id']}` zodra de bestelling is afgerond.*"
        )
        await log_bestelling(guild, bestelling_embed(b, f"🆕 Nieuwe bestelling #{b['id']}"))
    else:
        e = embed(
            "🎫 Nieuw ticket",
            f"Hoi {user.mention}! Vertel welke bot je wilt bestellen of waar je hulp bij nodig hebt."
        )
    ping = staff.mention if staff else ""
    await kanaal.send(content=f"{user.mention} {ping}", embed=e, view=SluitKnop())
    await interaction.response.send_message(f"Je ticket is aangemaakt: {kanaal.mention}", ephemeral=True)

class TicketKnop(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Open een ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="ticket_openen_persistent")
    async def openen(self, interaction: discord.Interaction, button: ui.Button):
        await maak_ticket(interaction)

class SluitKnop(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Ticket sluiten", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_sluiten_persistent")
    async def sluiten(self, interaction: discord.Interaction, button: ui.Button):
        kanaal = interaction.channel
        staff = discord.utils.get(interaction.guild.roles, name=STAFF_ROL)
        is_eigenaar = kanaal.topic == f"ticket:{interaction.user.id}"
        is_staff_user = staff in interaction.user.roles if staff else False
        if not (is_eigenaar or is_staff_user or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("Alleen de ticket-eigenaar of staff kan dit sluiten.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Ticket wordt over 5 seconden gesloten...")
        await asyncio.sleep(5)
        await kanaal.delete()

class ProductSelect(ui.Select):
    def __init__(self):
        opties = [
            discord.SelectOption(
                label=p["naam"][:100],
                description=f"{euro(p['prijs'])} - {p['omschrijving']}"[:100],
                value=str(p["id"]),
            )
            for p in SHOP["producten"][:25]
        ]
        super().__init__(placeholder="Kies een product...", options=opties, custom_id="shop_select_persistent")

    async def callback(self, interaction: discord.Interaction):
        product = vind_product_id(int(self.values[0]))
        if product is None:
            await interaction.response.send_message("Dit product bestaat niet meer.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=product_embed(product), view=BestelKnop(product["id"]), ephemeral=True
        )

class ShopView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProductSelect())

class BestelKnop(ui.View):
    def __init__(self, product_id):
        super().__init__(timeout=300)
        self.product_id = product_id

    @ui.button(label="Bestel dit product", emoji="🛒", style=discord.ButtonStyle.success)
    async def bestel(self, interaction: discord.Interaction, button: ui.Button):
        product = vind_product_id(self.product_id)
        if product is None:
            await interaction.response.send_message("Dit product bestaat niet meer.", ephemeral=True)
            return
        await maak_ticket(interaction, product)

# ==========================================
# SHUTDOWN / STARTUP FUNCTIONALITEIT
# ==========================================
def overwrites_naar_data(kanaal):
    data = []
    for target, ow in kanaal.overwrites.items():
        allow, deny = ow.pair()
        data.append({
            "id": target.id,
            "kind": "role" if isinstance(target, discord.Role) else "member",
            "allow": allow.value,
            "deny": deny.value,
        })
    return data

def data_naar_overwrites(guild, data):
    resultaat = {}
    for item in data:
        target = guild.get_role(item["id"]) if item["kind"] == "role" else guild.get_member(item["id"])
        if target is None:
            continue
        resultaat[target] = discord.PermissionOverwrite.from_pair(
            discord.Permissions(item["allow"]), discord.Permissions(item["deny"])
        )
    return resultaat

def maak_snapshot(guild, behoud_ids):
    categorieen = []
    for c in sorted(guild.categories, key=lambda c: c.position):
        if c.id in behoud_ids:
            continue
        categorieen.append({"id": c.id, "name": c.name, "overwrites": overwrites_naar_data(c)})

    kanalen = []
    for ch in sorted(guild.channels, key=lambda c: c.position):
        if isinstance(ch, discord.CategoryChannel) or ch.id in behoud_ids:
            continue
        item = {"name": ch.name, "category_id": ch.category_id, "overwrites": overwrites_naar_data(ch)}
        if isinstance(ch, discord.StageChannel):
            item["type"] = "stage"
        elif isinstance(ch, discord.VoiceChannel):
            item["type"] = "voice"
            item["user_limit"] = ch.user_limit
        elif isinstance(ch, discord.TextChannel):
            item["type"] = "news" if ch.is_news() else "text"
            item["topic"] = ch.topic
            item["nsfw"] = ch.nsfw
            item["slowmode"] = ch.slowmode_delay
        elif isinstance(ch, discord.ForumChannel):
            item["type"] = "forum"
            item["topic"] = ch.topic
        else:
            continue
        kanalen.append(item)

    return {"categorieen": categorieen, "kanalen": kanalen}

def shutdown_embed():
    e = discord.Embed(
        title="🔴 De server is gesloten",
        description=f"Beste leden,\n\n**{SERVERNAAM}** is tijdelijk gesloten.",
        colour=0xED4245,
    )
    e.set_footer(text=SERVERNAAM)
    return e

def startup_embed():
    e = discord.Embed(
        title="🟢 De server is weer open!",
        description=f"Goed nieuws: **{SERVERNAAM}** is weer online!",
        colour=0x57F287,
    )
    e.set_footer(text=SERVERNAAM)
    return e

async def voer_shutdown_uit(interaction: discord.Interaction):
    guild = interaction.guild
    mededeling = guild.get_channel(MEDEDELING_KANAAL_ID)

    behoud = {mededeling.id}
    if mededeling.category_id:
        behoud.add(mededeling.category_id)

    snapshot = maak_snapshot(guild, behoud)
    STATE_BESTAND.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    await mededeling.send(
        content="@everyone",
        embed=shutdown_embed(),
        allowed_mentions=discord.AllowedMentions(everyone=True),
    )

    teller, mislukt = 0, []
    te_verwijderen = [c for c in guild.channels if c.id not in behoud]
    te_verwijderen.sort(key=lambda c: isinstance(c, discord.CategoryChannel))
    for ch in te_verwijderen:
        try:
            await ch.delete(reason="Server shutdown")
            teller += 1
        except discord.HTTPException as err:
            mislukt.append(f"{ch.name} ({err.text or 'fout'})")

    tekst = f"✅ Shutdown klaar. {teller} kanalen verwijderd."
    if mislukt:
        tekst += "\n⚠️ Niet verwijderd: " + ", ".join(mislukt)
    try:
        await interaction.edit_original_response(content=tekst, view=None)
    except discord.HTTPException:
        pass

class BevestigShutdown(ui.View):
    def __init__(self, gebruiker_id):
        super().__init__(timeout=60)
        self.gebruiker_id = gebruiker_id

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.gebruiker_id:
            await interaction.response.send_message("Dit is niet jouw bevestiging.", ephemeral=True)
            return False
        return True

    @ui.button(label="Ja, sluit de server", emoji="🔴", style=discord.ButtonStyle.danger)
    async def ja(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="⏳ Shutdown bezig...", view=None)
        await voer_shutdown_uit(interaction)

    @ui.button(label="Annuleren", style=discord.ButtonStyle.secondary)
    async def nee(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Geannuleerd.", view=None)

def mag_shutdown(member) -> bool:
    return any(rol.id == SHUTDOWN_ROL_ID for rol in member.roles)

# ==========================================
# BOT KLASSE & SETUP HOOK
# ==========================================
class FinnsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(VerificationView())
        self.add_view(TicketKnop())
        self.add_view(SluitKnop())
        self.add_view(ShopView())

        try:
            synced = await self.tree.sync()
            print(f"✅ Globaal gesynchroniseerd ({len(synced)} unieke commando's).")
        except Exception as e:
            print(f"⚠️ Fout bij synchroniseren van commando's: {e}")
        
        check_twee_wekelijkse_overzicht.start()

bot = FinnsBot()

# ==========================================
# PERIODIEKE TAAK
# ==========================================
@tasks.loop(hours=1)
async def check_twee_wekelijkse_overzicht():
    nu = datetime.now(timezone.utc)
    if nu.weekday() == 6 and nu.hour == 12 and (nu.isocalendar().week % 2 == 0):
        kanaal = bot.get_channel(WEEK_OVERZICHT_KANAAL_ID)
        if kanaal:
            guild = bot.get_guild(GUILD_ID)
            totaal_leden = guild.member_count if guild else "Onbekend"
            
            e = discord.Embed(
                title="📊 Twee-wekelijks Server Overzicht",
                description=f"Overzicht van de afgelopen 2 weken in **{SERVERNAAM}**!",
                color=KLEUR,
                timestamp=nu
            )
            e.add_field(name="👋 Nieuwe Leden", value=f"**{WEEK_STATS['joins']}**", inline=True)
            e.add_field(name="✅ Geverifieerd", value=f"**{WEEK_STATS['verificaties']}**", inline=True)
            e.add_field(name="👥 Totaal Leden", value=f"**{totaal_leden}**", inline=True)
            e.add_field(name="🛒 Nieuwe Bestellingen", value=f"**{WEEK_STATS['nieuwe_bestellingen']}**", inline=True)
            e.add_field(name="🎉 Afgerond", value=f"**{WEEK_STATS['afgeronde_bestellingen']}**", inline=True)
            e.set_footer(text=SERVERNAAM)

            await kanaal.send(embed=e)

            WEEK_STATS["joins"] = 0
            WEEK_STATS["verificaties"] = 0
            WEEK_STATS["nieuwe_bestellingen"] = 0
            WEEK_STATS["afgeronde_bestellingen"] = 0
            bewaar_stats(WEEK_STATS)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="Bots verkopen | /help"))
    print(f"🤖 Ingelogd als {bot.user} (ID: {bot.user.id})")
    print("--------------------------------------------------")

@bot.event
async def on_member_join(member: discord.Member):
    WEEK_STATS["joins"] += 1
    bewaar_stats(WEEK_STATS)

    auto_rol = member.guild.get_role(AUTOMATIC_JOIN_ROLE_ID)
    if auto_rol:
        try:
            await member.add_roles(auto_rol)
        except discord.Forbidden:
            pass

    welkom_kanaal = member.guild.get_channel(KANAAL_WELKOM_ID)
    if welkom_kanaal:
        e = discord.Embed(
            title=f"👋 Welkom bij {member.guild.name}!",
            description=(
                f"Hoi {member.mention}, erg leuk dat je er bent!\n\n"
                "• Verifieer jezelf in <#1557822033545527493>\n"
                "• Bekijk de regels in <#1557822036154384457>\n"
                "• Check de prijzen in <#1557822048279994458>\n"
                "• Bestel een bot via <#1557822059646554194>"
            ),
            colour=KLEUR
        )
        if member.display_avatar:
            e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text=f"{SERVERNAAM} • Lid #{len(member.guild.members)}")
        
        await welkom_kanaal.send(content=f"Welkom {member.mention}!", embed=e)

@bot.event
async def on_member_remove(member: discord.Member):
    welkom_kanaal = member.guild.get_channel(KANAAL_WELKOM_ID)
    if not welkom_kanaal:
        return

    try:
        async for message in welkom_kanaal.history(limit=100):
            if message.author == bot.user:
                if str(member.id) in message.content or (message.embeds and str(member.id) in message.embeds[0].description):
                    await message.delete()
                    break
    except Exception:
        pass

# ==========================================
# SLASH COMMANDO'S (UNIEK)
# ==========================================
@bot.tree.command(name="help", description="Laat alle commands zien")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=help_embed(is_staff(interaction.user)), ephemeral=True)

@bot.tree.command(name="bots", description="Bekijk de bots die we verkopen")
async def bots_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=bots_embed())

@bot.tree.command(name="prijzen", description="Bekijk de prijslijst")
async def prijzen_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=prijzen_embed())

@bot.tree.command(name="shop", description="Open de winkel en kies een product")
async def shop_cmd(interaction: discord.Interaction):
    if not SHOP["producten"]:
        await interaction.response.send_message("De winkel is nog leeg!", ephemeral=True)
        return
    e = bots_embed("🛒 Winkel")
    await interaction.response.send_message(embed=e, view=ShopView())

@bot.tree.command(name="bestellen", description="Bestel een product (opent een privé ticket)")
@app_commands.describe(product="Welk product wil je?", code="Heb je een kortingscode?")
@app_commands.autocomplete(product=product_autocomplete)
async def bestellen_cmd(interaction: discord.Interaction, product: str = None, code: str = None):
    gekozen = None
    if product:
        gekozen = vind_product(product)
        if gekozen is None:
            await interaction.response.send_message("Dat product bestaat niet.", ephemeral=True)
            return
    await maak_ticket(interaction, gekozen, code)

@bot.tree.command(name="kortingscodegebruik", description="Controleer of een kortingscode geldig is")
@app_commands.describe(code="Voer de kortingscode in")
async def kortingscodegebruik_cmd(interaction: discord.Interaction, code: str):
    sleutel = code.strip().upper()
    if sleutel in SHOP["kortingscodes"]:
        procent = SHOP["kortingscodes"][sleutel]
        await interaction.response.send_message(f"🎉 Code `{sleutel}` geeft **{procent}% korting**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Code `{sleutel}` is **ongeldig**.", ephemeral=True)

@bot.tree.command(name="mijnbestellingen", description="Bekijk je eigen bestellingen")
async def mijnbestellingen_cmd(interaction: discord.Interaction):
    mijn = [b for b in SHOP["bestellingen"] if b["gebruiker_id"] == interaction.user.id]
    if not mijn:
        await interaction.response.send_message("Je hebt nog niets besteld.", ephemeral=True)
        return
    e = embed("📦 Jouw bestellingen")
    for b in mijn[-10:]:
        e.add_field(
            name=f"{STATUS_ICOON[b['status']]} #{b['id']}  {b['product_naam']}",
            value=f"{euro(b['prijs'])} • {b['status']}",
            inline=False,
        )
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="review", description="Laat een review achter over onze service of bot")
@app_commands.describe(sterren="Aantal sterren (1 t/m 5)", tekst="Je ervaring of beoordeling")
async def review_cmd(
    interaction: discord.Interaction,
    sterren: app_commands.Range[int, 1, 5],
    tekst: app_commands.Range[str, 5, 500],
):
    kanaal = interaction.guild.get_channel(KANAAL_REVIEWS_ID)
    if kanaal is None:
        kanaal = discord.utils.get(interaction.guild.text_channels, name="reviews")
        
    if kanaal is None:
        await interaction.response.send_message("Het review-kanaal is niet gevonden.", ephemeral=True)
        return

    e = discord.Embed(
        title="⭐" * sterren + "☆" * (5 - sterren) + " Review",
        description=tekst,
        colour=0xFEE75C,
    )
    e.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
    e.set_footer(text=SERVERNAAM)
    
    await kanaal.send(embed=e)
    await interaction.response.send_message("Bedankt voor je review! 💙", ephemeral=True)

@bot.tree.command(name="serverinfo", description="Info over deze server")
async def serverinfo_cmd(interaction: discord.Interaction):
    g = interaction.guild
    e = embed(f"ℹ️ {g.name}")
    e.add_field(name="Leden", value=str(g.member_count))
    e.add_field(name="Kanalen", value=str(len(g.channels)))
    e.add_field(name="Aangemaakt", value=discord.utils.format_dt(g.created_at, "D"))
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="ping", description="Test hoe snel de bot reageert")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)} ms")

@bot.tree.command(name="berichtbot", description="Stuur een bericht (en optioneel een afbeelding) als de bot (staff)")
@app_commands.describe(
    bericht="Het tekstbericht dat de bot moet sturen",
    afbeelding="Upload optioneel een afbeelding die meegestuurd moet worden"
)
async def berichtbot_cmd(
    interaction: discord.Interaction,
    bericht: str,
    afbeelding: discord.Attachment = None
):
    if not await staff_check(interaction):
        return

    bestand = None
    if afbeelding:
        bestand = await afbeelding.to_file()

    await interaction.channel.send(content=bericht, file=bestand)
    await interaction.response.send_message("✅ Bericht succesvol verzonden!", ephemeral=True)

@bot.tree.command(name="setup_embeds", description="Plaats mooie berichten in de infokanalen op basis van ID's (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_embeds_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    g = interaction.guild

    doelen_by_id = {
        KANAAL_VERIFICATIE_ID: (
            embed("Verificatie", "Klik op de knop hieronder om jezelf te verifiëren."),
            VerificationView(),
            "#verificatie"
        ),
        KANAAL_WELKOM_ID: (welkom_embed(), None, "#welkom"),
        KANAAL_REGELS_ID: (regels_embed(), None, "#regels"),
        KANAAL_SUPPORT_ID: (support_embed(), None, "#vragenensupport"),
        KANAAL_PRIJZEN_ID: (prijzen_embed(), None, "#prijzen"),
        KANAAL_BESTELLEN_ID: (
            embed("🎫 Bestellen", "Klik op de knop hieronder om een privé ticket te openen."),
            TicketKnop(),
            "#bestellen"
        ),
    }

    geplaatst, ontbreekt = [], []
    for ch_id, (e, view, label) in doelen_by_id.items():
        kanaal = g.get_channel(ch_id)
        if kanaal is None:
            ontbreekt.append(f"{label} ({ch_id})")
            continue
        if view:
            await kanaal.send(embed=e, view=view)
        else:
            await kanaal.send(embed=e)
        geplaatst.append(label)

    tekst = "✅ Geplaatst in: " + ", ".join(geplaatst) if geplaatst else "Niets geplaatst."
    if ontbreekt:
        tekst += "\n⚠️ Kanaal-ID niet gevonden: " + ", ".join(ontbreekt)
    await interaction.followup.send(tekst, ephemeral=True)

@bot.tree.command(name="product_toevoegen", description="Voeg een product toe aan de winkel (staff)")
@app_commands.describe(naam="Naam", omschrijving="Korte omschrijving", prijs="Prijs in euro")
async def product_toevoegen_cmd(
    interaction: discord.Interaction,
    naam: app_commands.Range[str, 2, 80],
    omschrijving: app_commands.Range[str, 2, 200],
    prijs: app_commands.Range[float, 0.01, 100000.0],
):
    if not await staff_check(interaction):
        return
    if any(p["naam"].lower() == naam.lower() for p in SHOP["producten"]):
        await interaction.response.send_message("Er is al een product met die naam.", ephemeral=True)
        return
    p = {"id": SHOP["volgend_product"], "naam": naam, "omschrijving": omschrijving, "prijs": round(prijs, 2)}
    SHOP["volgend_product"] += 1
    SHOP["producten"].append(p)
    bewaar_shop()
    await interaction.response.send_message("✅ Product toegevoegd:", embed=product_embed(p), ephemeral=True)

@bot.tree.command(name="product_bewerken", description="Pas een product aan (staff)")
@app_commands.describe(product="Welk product?", nieuwe_naam="Nieuwe naam", omschrijving="Nieuwe omschrijving", prijs="Nieuwe prijs")
@app_commands.autocomplete(product=product_autocomplete)
async def product_bewerken_cmd(
    interaction: discord.Interaction,
    product: str,
    nieuwe_naam: app_commands.Range[str, 2, 80] = None,
    omschrijving: app_commands.Range[str, 2, 200] = None,
    prijs: app_commands.Range[float, 0.01, 100000.0] = None,
):
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
    if prijs:
        p["prijs"] = round(prijs, 2)
    bewaar_shop()
    await interaction.response.send_message("✅ Product aangepast:", embed=product_embed(p), ephemeral=True)

@bot.tree.command(name="product_verwijderen", description="Verwijder een product uit de winkel (staff)")
@app_commands.describe(product="Welk product?")
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
    await interaction.response.send_message(f"🗑️ **{p['naam']}** is verwijderd.", ephemeral=True)

@bot.tree.command(name="bestellingen", description="Bekijk alle open bestellingen (staff)")
async def bestellingen_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction):
        return
    open_b = [b for b in SHOP["bestellingen"] if b["status"] == "open"]
    if not open_b:
        await interaction.response.send_message("Geen open bestellingen. 🎉", ephemeral=True)
        return
    e = embed(f"🟡 Open bestellingen ({len(open_b)})")
    for b in open_b[:25]:
        ticket = f"<#{b['ticket_kanaal_id']}>" if interaction.guild.get_channel(b["ticket_kanaal_id"]) else "gesloten"
        e.add_field(
            name=f"#{b['id']}  {b['product_naam']}",
            value=f"<@{b['gebruiker_id']}> • {euro(b['prijs'])} • {ticket}",
            inline=False,
        )
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="afronden", description="Rond een bestelling af (staff)")
@app_commands.describe(bestelling_id="Het nummer van de bestelling")
async def afronden_cmd(interaction: discord.Interaction, bestelling_id: int):
    if not await staff_check(interaction):
        return
    b = vind_bestelling(bestelling_id)
    if b is None:
        await interaction.response.send_message("Bestelling niet gevonden.", ephemeral=True)
        return
    if b["status"] != "open":
        await interaction.response.send_message(f"Deze bestelling is al {b['status']}.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    b["status"] = "afgerond"
    b["afgerond_door"] = interaction.user.id
    bewaar_shop()

    WEEK_STATS["afgeronde_bestellingen"] += 1
    bewaar_stats(WEEK_STATS)

    lid = guild.get_member(b["gebruiker_id"])
    klant_rol = guild.get_role(KLANT_ROL_ID)
    if lid:
        if klant_rol:
            try:
                await lid.add_roles(klant_rol)
            except discord.Forbidden:
                print("⚠️ Bot mist permissie 'Rollen beheren' om de Klant-rol toe te kennen!")
        else:
            print(f"⚠️ Kon de Klant-rol met ID {KLANT_ROL_ID} niet vinden in de server!")

    ticket = guild.get_channel(b["ticket_kanaal_id"])
    if ticket:
        await ticket.send(f"✅ Bestelling **#{b['id']} ({b['product_naam']})** is afgerond!")
    await log_bestelling(guild, bestelling_embed(b, f"✅ Bestelling #{b['id']} afgerond door {interaction.user.display_name}"))
    await interaction.followup.send(f"✅ Bestelling #{b['id']} afgerond.", ephemeral=True)

@bot.tree.command(name="annuleren", description="Annuleer een bestelling (staff/klant)")
@app_commands.describe(bestelling_id="Het nummer van de bestelling")
async def annuleren_cmd(interaction: discord.Interaction, bestelling_id: int):
    b = vind_bestelling(bestelling_id)
    if b is None:
        await interaction.response.send_message("Bestelling niet gevonden.", ephemeral=True)
        return
    if not (is_staff(interaction.user) or b["gebruiker_id"] == interaction.user.id):
        await interaction.response.send_message("Je kunt alleen je eigen bestellingen annuleren.", ephemeral=True)
        return
    if b["status"] != "open":
        await interaction.response.send_message(f"Deze bestelling is al {b['status']}.", ephemeral=True)
        return
    b["status"] = "geannuleerd"
    bewaar_shop()
    await log_bestelling(interaction.guild, bestelling_embed(b, f"🔴 Bestelling #{b['id']} geannuleerd door {interaction.user.display_name}"))
    await interaction.response.send_message(f"🔴 Bestelling #{b['id']} is geannuleerd.", ephemeral=True)

@bot.tree.command(name="kortingscode_maken", description="Maak een kortingscode (staff)")
@app_commands.describe(code="De code", procent="Korting in procenten")
async def kortingscode_maken_cmd(
    interaction: discord.Interaction,
    code: app_commands.Range[str, 3, 20],
    procent: app_commands.Range[int, 1, 90],
):
    if not await staff_check(interaction):
        return
    sleutel = code.strip().upper()
    SHOP["kortingscodes"][sleutel] = procent
    bewaar_shop()
    await interaction.response.send_message(f"✅ Code `{sleutel}` geeft **{procent}%** korting.", ephemeral=True)

@bot.tree.command(name="kortingscode_verwijderen", description="Verwijder een kortingscode (staff)")
@app_commands.describe(code="De code")
async def kortingscode_verwijderen_cmd(interaction: discord.Interaction, code: str):
    if not await staff_check(interaction):
        return
    sleutel = code.strip().upper()
    if SHOP["kortingscodes"].pop(sleutel, None) is None:
        await interaction.response.send_message("Die code bestaat niet.", ephemeral=True)
        return
    bewaar_shop()
    await interaction.response.send_message(f"🗑️ Code `{sleutel}` is verwijderd.", ephemeral=True)

@bot.tree.command(name="kortingscodes", description="Lijst van alle kortingscodes (staff)")
async def kortingscodes_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction):
        return
    if not SHOP["kortingscodes"]:
        await interaction.response.send_message("Er zijn geen kortingscodes.", ephemeral=True)
        return
    regels = "\n".join(f"`{c}`: {p}%" for c, p in SHOP["kortingscodes"].items())
    await interaction.response.send_message(embed=embed("🏷️ Kortingscodes", regels), ephemeral=True)

@bot.tree.command(name="shopstats", description="Omzet en populairste product (staff)")
async def shopstats_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction):
        return
    alle = SHOP["bestellingen"]
    afgerond = [b for b in alle if b["status"] == "afgerond"]
    tellingen = {}
    for b in afgerond:
        tellingen[b["product_naam"]] = tellingen.get(b["product_naam"], 0) + 1
    populair = max(tellingen, key=tellingen.get) if tellingen else "nog geen verkopen"

    e = embed("📊 Shop-statistieken")
    e.add_field(name="Omzet", value=euro(sum(b["prijs"] for b in afgerond)))
    e.add_field(name="Afgerond", value=str(len(afgerond)))
    e.add_field(name="Open", value=str(sum(b["status"] == "open" for b in alle)))
    e.add_field(name="Geannuleerd", value=str(sum(b["status"] == "geannuleerd" for b in alle)))
    e.add_field(name="Populairste product", value=populair, inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="shutdown", description="Server sluiten")
async def shutdown_cmd(interaction: discord.Interaction):
    if not mag_shutdown(interaction.user):
        await interaction.response.send_message("Geen toestemming.", ephemeral=True)
        return
    await interaction.response.send_message(
        "⚠️ **Weet je het zeker?** Alle kanalen worden verwijderd.",
        view=BevestigShutdown(interaction.user.id),
        ephemeral=True,
    )

@bot.tree.command(name="startup", description="Server openen")
async def startup_cmd(interaction: discord.Interaction):
    if not mag_shutdown(interaction.user):
        await interaction.response.send_message("Geen toestemming.", ephemeral=True)
        return
    if not STATE_BESTAND.exists():
        await interaction.response.send_message("Geen opgeslagen indeling gevonden.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    data = json.loads(STATE_BESTAND.read_text(encoding="utf-8"))

    mapping = {}
    for cat in data["categorieen"]:
        nieuw = await guild.create_category(cat["name"], overwrites=data_naar_overwrites(guild, cat["overwrites"]))
        mapping[cat["id"]] = nieuw

    aantal = 0
    for item in data["kanalen"]:
        categorie = mapping.get(item["category_id"])
        ow = data_naar_overwrites(guild, item["overwrites"])
        naam = item["name"]
        try:
            soort = item["type"]
            if soort in ("text", "news"):
                await guild.create_text_channel(naam, category=categorie, overwrites=ow)
            elif soort == "voice":
                await guild.create_voice_channel(naam, category=categorie, overwrites=ow)
            aantal += 1
        except discord.HTTPException:
            pass

    STATE_BESTAND.unlink()
    mededeling = guild.get_channel(MEDEDELING_KANAAL_ID)
    if mededeling:
        await mededeling.send(content="@everyone", embed=startup_embed(), allowed_mentions=discord.AllowedMentions(everyone=True))

    await interaction.followup.send(f"✅ Startup klaar. {aantal} kanalen teruggezet.", ephemeral=True)

@bot.tree.command(name="ban", description="Ban een gebruiker van de server.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban_command(interaction: discord.Interaction, member: discord.Member, reason: str = "Geen reden opgegeven"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"Gebruiker {member.mention} is gebanned. Reden: {reason}", ephemeral=True)

@bot.tree.command(name="kick", description="Kick een gebruiker uit de server.")
@app_commands.checks.has_permissions(kick_members=True)
async def kick_command(interaction: discord.Interaction, member: discord.Member, reason: str = "Geen reden opgegeven"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"Gebruiker {member.mention} is gekicked. Reden: {reason}", ephemeral=True)

@bot.tree.command(name="clear", description="Verwijder berichten in het kanaal.")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear_command(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"{amount} berichten verwijderd.", ephemeral=True)

@bot.tree.command(name="purge", description="Verwijder berichten in het kanaal.")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge_command(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"{amount} berichten verwijderd.", ephemeral=True)

# Start de bot
bot.run(TOKEN)
