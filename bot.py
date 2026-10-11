import asyncio
import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
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

CHANNEL_BETAAL_REVIEW = 1558743224384757820      
CHANNEL_BETAAL_CONFIRM = 1558743246883131432     

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

pending_pay_submissions = {}

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

def laad_stats():
    if STATS_BESTAND.exists():
        return json.loads(STATS_BESTAND.read_text(encoding="utf-8"))
    return {"joins": 0, "verificaties": 0, "nieuwe_bestellingen": 0, "afgeronde_bestellingen": 0}

def bewaar_stats(stats):
    STATS_BESTAND.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

WEEK_STATS = laad_stats()
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
    e.add_field(name="Security Bot\n€7,50", value="Automoderatie, kick, ban, mute, warn, clear, slowmode.", inline=False)
    e.add_field(name="Normale Bot\n€10,00", value="Een bot met 10 custom commands en tutorial.", inline=False)
    e.add_field(name="Premium Bot\n€15,00", value="15 custom commands, Security Bot inbegrepen, 24/7 hosting.", inline=False)
    e.set_footer(text=SERVERNAAM)
    return e

def welkom_embed():
    return embed(f"Welkom bij {SERVERNAAM}! 🤖", "Hier vind je custom Discord-bots voor jouw server.")

def regels_embed():
    tekst = "\n".join(f"**{i}.** {regel}" for i, regel in enumerate(REGELS, 1))
    return embed("📜 Serverregels", tekst)

def support_embed():
    return embed("❓ Vragen & Support", "Heb je een vraag? Open gerust een ticket via **#bestellen**!")

def help_embed(staff=False):
    e = embed(
        "📖 Commands",
        "`/shop`  open de winkel\n"
        "`/bots`  de bots die we verkopen\n"
        "`/prijzen`  de prijslijst\n"
        "`/bestellen`  bestel direct een product\n"
        "`/mijnbestellingen`  je bestelgeschiedenis\n"
        "`/review`  laat een review achter\n"
        "`/serverinfo`  info over de server\n"
        "`/ping`  snelheidstest",
    )
    if staff:
        e.add_field(
            name="🔒 Staff",
            value=(
                "`/berichtbot` `/betaalticket` `/giveaway` `/bestellingen` `/afronden` `/annuleren` "
                "`/product_toevoegen` `/product_bewerken` `/product_verwijderen` `/kortingscode_maken` "
                "`/kortingscode_verwijderen` `/kortingscodes` `/shopstats` `/ban` `/kick` `/clear` `/purge`"
            ),
            inline=False,
        )
    return e

def verwerk_tijd(tijd_str: str) -> int:
    match = re.match(r"^(\d+)([s|m|h|d])$", tijd_str.lower().strip())
    if not match:
        return None
    aantal, eenheid = int(match.group(1)), match.group(2)
    vermenigvuldiger = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return aantal * vermenigvuldiger[eenheid]

class GiveawayView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.deelnemers = set()

    @ui.button(label="Meedoen 🎉", style=discord.ButtonStyle.blurple, custom_id="giveaway_join_btn_persistent")
    async def meedoen(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id in self.deelnemers:
            self.deelnemers.remove(interaction.user.id)
            await interaction.response.send_message("❌ Je hebt je uitgeschreven voor de giveaway.", ephemeral=True)
        else:
            self.deelnemers.add(interaction.user.id)
            await interaction.response.send_message("🎉 Je doet nu mee aan de giveaway!", ephemeral=True)
        
        button.label = f"Meedoen 🎉 ({len(self.deelnemers)})"
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

class BetaalAcceptModal(ui.Modal, title="Aanvraag Accepteren & Betaallink"):
    betaallink = ui.TextInput(label="Betaallink", placeholder="https://...", required=True)
    toelichting = ui.TextInput(label="Optionele toelichting", style=discord.TextStyle.paragraph, required=False)

    def __init__(self, target_member: discord.Member, message: discord.Message, view_inst: ui.View):
        super().__init__()
        self.target_member = target_member
        self.message = message
        self.view_inst = view_inst

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        for child in self.view_inst.children:
            child.disabled = True
        try:
            await self.message.edit(view=self.view_inst)
        except Exception:
            pass
        if self.target_member.id in pending_pay_submissions:
            pending_pay_submissions[self.target_member.id]["status"] = "AWAITING_PAYMENT"

        dm_text = f"✅ **Jouw aanvraag is goedgekeurd!**\n🔗 **Betaallink:** {self.betaallink.value}\nTyp **`betaald`** in deze chat zodra je hebt betaald."
        try:
            await self.target_member.send(dm_text)
            await interaction.followup.send("✅ Betaallink verstuurd!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Kon geen DM sturen naar deze gebruiker.", ephemeral=True)

class BetaalDenyModal(ui.Modal, title="Aanvraag Afwijzen"):
    reden = ui.TextInput(label="Reden van afwijzing", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, target_member: discord.Member, message: discord.Message, view_inst: ui.View):
        super().__init__()
        self.target_member = target_member
        self.message = message
        self.view_inst = view_inst

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        for child in self.view_inst.children:
            child.disabled = True
        try:
            await self.message.edit(view=self.view_inst)
        except Exception:
            pass
        pending_pay_submissions.pop(self.target_member.id, None)
        try:
            await self.target_member.send(f"❌ Aanvraag afgewezen.\n**Reden:** {self.reden.value}")
        except discord.Forbidden:
            pass
        await interaction.followup.send("Aanvraag afgewezen.", ephemeral=True)

class BetaalReviewView(ui.View):
    def __init__(self, target_member: discord.Member):
        super().__init__(timeout=None)
        self.target_member = target_member

    @ui.button(label="Accepteren", style=discord.ButtonStyle.green, custom_id="pay_review_accept")
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("Alleen staff.", ephemeral=True)
            return
        await interaction.response.send_modal(BetaalAcceptModal(self.target_member, interaction.message, self))

    @ui.button(label="Afwijzen", style=discord.ButtonStyle.red, custom_id="pay_review_deny")
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("Alleen staff.", ephemeral=True)
            return
        await interaction.response.send_modal(BetaalDenyModal(self.target_member, interaction.message, self))

class ConfirmDeliveryModal(ui.Modal, title="Levering & Bestand"):
    bericht = ui.TextInput(label="Bericht aan klant", style=discord.TextStyle.paragraph, required=True)
    downloadfile = ui.TextInput(label="Downloadlink", required=True, placeholder="https://...")

    def __init__(self, target_member: discord.Member, message: discord.Message, view_inst: ui.View):
        super().__init__()
        self.target_member = target_member
        self.message = message
        self.view_inst = view_inst

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        for child in self.view_inst.children:
            child.disabled = True
        try:
            await self.message.edit(view=self.view_inst)
        except Exception:
            pass
        e = discord.Embed(title="🎉 Bestelling geleverd!", description=f"{self.bericht.value}\n\n📦 **Link:** {self.downloadfile.value}", color=discord.Color.green())
        try:
            await self.target_member.send(embed=e)
            await interaction.followup.send("✅ Levering verzonden!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Kon geen DM sturen.", ephemeral=True)
        pending_pay_submissions.pop(self.target_member.id, None)

class ConfirmDenyModal(ui.Modal, title="Betaling Afwijzen"):
    reden = ui.TextInput(label="Reden", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, target_member: discord.Member, message: discord.Message, view_inst: ui.View):
        super().__init__()
        self.target_member = target_member
        self.message = message
        self.view_inst = view_inst

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        for child in self.view_inst.children:
            child.disabled = True
        try:
            await self.message.edit(view=self.view_inst)
        except Exception:
            pass
        try:
            await self.target_member.send(f"❌ Betaling afgewezen. Reden: {self.reden.value}")
        except discord.Forbidden:
            pass
        await interaction.followup.send("Betaling afgewezen.", ephemeral=True)
        pending_pay_submissions.pop(self.target_member.id, None)

class BetaalConfirmView(ui.View):
    def __init__(self, target_member: discord.Member):
        super().__init__(timeout=None)
        self.target_member = target_member

    @ui.button(label="Accepteren", style=discord.ButtonStyle.green, custom_id="pay_confirm_accept")
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user): return
        await interaction.response.send_modal(ConfirmDeliveryModal(self.target_member, interaction.message, self))

    @ui.button(label="Afwijzen", style=discord.ButtonStyle.red, custom_id="pay_confirm_deny")
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user): return
        await interaction.response.send_modal(ConfirmDenyModal(self.target_member, interaction.message, self))

class PayStepImageSentView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @ui.button(label="Afbeelding verstuurd", style=discord.ButtonStyle.blurple, emoji="📸")
    async def image_sent(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        data = pending_pay_submissions.get(self.user_id)
        if not data or not data.get("image_url"):
            await interaction.followup.send("⚠️ Geen afbeelding ontvangen!", ephemeral=True)
            return
        for child in self.children: child.disabled = True
        try: await interaction.message.edit(view=self)
        except Exception: pass
        target_channel = bot.get_channel(CHANNEL_BETAAL_REVIEW)
        if target_channel:
            e = discord.Embed(title="💳 Nieuwe Betaalaanvraag", description=f"**Klant:** {interaction.user.mention}\n**Product:** {data['product']}", color=discord.Color.blue())
            e.set_image(url=data["image_url"])
            await target_channel.send(embed=e, view=BetaalReviewView(interaction.user))
            await interaction.followup.send("✅ Aanvraag ingediend!", ephemeral=True)

class PayStepMsgSubmittedView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @ui.button(label="Bericht indienen", style=discord.ButtonStyle.green, emoji="📩")
    async def msg_submitted(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        data = pending_pay_submissions.get(self.user_id)
        if not data or not data.get("product"):
            await interaction.followup.send("⚠️ Geen productnaam getypt!", ephemeral=True)
            return
        for child in self.children: child.disabled = True
        try: await interaction.message.edit(view=self)
        except Exception: pass
        await interaction.user.send("📸 Stuur nu een afbeelding als bewijs:", view=PayStepImageSentView(self.user_id))

class BetaalStartView(ui.View):
    def __init__(self): super().__init__(timeout=None)

    @ui.button(label="Start Betaal Aanvraag", style=discord.ButtonStyle.success, emoji="💳", custom_id="betaal_start_btn_persistent")
    async def start_btn(self, interaction: discord.Interaction, button: ui.Button):
        user_id = interaction.user.id
        pending_pay_submissions[user_id] = {"product": None, "image_url": None, "status": "SETUP"}
        try:
            dm = await interaction.user.create_dm()
            await dm.send("Welk product wil je bestellen? Typ de naam hieronder:", view=PayStepMsgSubmittedView(user_id))
            await interaction.response.send_message("Check je DM!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Zet je DM's open!", ephemeral=True)

class LogModeratieView(ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id

    @ui.button(label="Ban user", emoji="🔨", style=discord.ButtonStyle.danger, custom_id="log_ban_user_btn")
    async def ban_user(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user): return
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.guild.ban(discord.Object(id=self.target_user_id), reason="Via logknoppen")
            for child in self.children: child.disabled = True
            await interaction.message.edit(view=self)
            await interaction.followup.send("🔨 Gebruiker gebanned.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Fout: {e}", ephemeral=True)

class VerificationModal(ui.Modal, title="Server Verificatie"):
    antwoord = ui.TextInput(label="Typ het woord: VERIFIED", placeholder="VERIFIED", required=True, max_length=20)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.antwoord.value.strip().upper() == "VERIFIED":
            guild = interaction.guild
            member = interaction.user
            v_role = guild.get_role(VERIFIED_ROLE_ID)
            unv_role = guild.get_role(UNVERIFIED_ROLE_ID)
            if v_role: await member.add_roles(v_role)
            if unv_role and unv_role in member.roles: await member.remove_roles(unv_role)
            await interaction.followup.send("Je bent geverifieerd!", ephemeral=True)
            WEEK_STATS["verificaties"] += 1
            bewaar_stats(WEEK_STATS)
        else:
            await interaction.followup.send("Onjuist antwoord!", ephemeral=True)

class VerificationView(ui.View):
    def __init__(self): super().__init__(timeout=None)
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
            await interaction.response.send_message("❌ Ongeldige code.", ephemeral=True)
            return
        procent, gebruikte_code = SHOP["kortingscodes"][sleutel], sleutel

    staff = discord.utils.get(guild.roles, name=STAFF_ROL)
    toegang = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    categorie = discord.utils.get(guild.categories, name=TICKET_CATEGORIE) or await guild.create_category(TICKET_CATEGORIE)
    
    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False), user: toegang, guild.me: toegang}
    if staff: overwrites[staff] = toegang

    kanaal = await guild.create_text_channel(f"ticket-{user.name}", category=categorie, topic=f"ticket:{user.id}", overwrites=overwrites)
    if product:
        b = maak_bestelling(user, product, procent, gebruikte_code, kanaal.id)
        e = bestelling_embed(b, f"🛒 Bestelling #{b['id']}")
        await log_bestelling(guild, bestelling_embed(b, f"🆕 Nieuwe bestelling #{b['id']}"))
    else:
        e = embed("🎫 Nieuw ticket", f"Hoi {user.mention}! Waar kunnen we je mee helpen?")
    await kanaal.send(content=f"{user.mention}", embed=e, view=SluitKnop())
    await interaction.response.send_message(f"Ticket aangemaakt: {kanaal.mention}", ephemeral=True)

class TicketKnop(ui.View):
    def __init__(self): super().__init__(timeout=None)
    @ui.button(label="Open een ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="ticket_openen_persistent")
    async def openen(self, interaction: discord.Interaction, button: ui.Button): await maak_ticket(interaction)

class SluitKnop(ui.View):
    def __init__(self): super().__init__(timeout=None)
    @ui.button(label="Ticket sluiten", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_sluiten_persistent")
    async def sluiten(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🔒 Ticket sluit over 5 seconden...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class ProductSelect(ui.Select):
    def __init__(self):
        opties = [discord.SelectOption(label=p["naam"][:100], value=str(p["id"])) for p in SHOP["producten"][:25]]
        super().__init__(placeholder="Kies een product...", options=opties, custom_id="shop_select_persistent")

    async def callback(self, interaction: discord.Interaction):
        p = vind_product_id(int(self.values[0]))
        if not p: return
        await interaction.response.send_message(embed=product_embed(p), view=BestelKnop(p["id"]), ephemeral=True)

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
        p = vind_product_id(self.product_id)
        if not p: return
        await maak_ticket(interaction, p)

def overwrites_naar_data(kanaal):
    return [{"id": t.id, "kind": "role" if isinstance(t, discord.Role) else "member", "allow": ow.pair()[0].value, "deny": ow.pair()[1].value} for t, ow in kanaal.overwrites.items()]

def data_naar_overwrites(guild, data):
    return {(guild.get_role(i["id"]) if i["kind"] == "role" else guild.get_member(i["id"])): discord.PermissionOverwrite.from_pair(discord.Permissions(i["allow"]), discord.Permissions(i["deny"])) for i in data if (guild.get_role(i["id"]) if i["kind"] == "role" else guild.get_member(i["id"]))}

def maak_snapshot(guild, behoud_ids):
    cats = [{"id": c.id, "name": c.name, "overwrites": overwrites_naar_data(c)} for c in guild.categories if c.id not in behoud_ids]
    chans = [{"name": ch.name, "category_id": ch.category_id, "overwrites": overwrites_naar_data(ch), "type": "text"} for ch in guild.channels if not isinstance(ch, discord.CategoryChannel) and ch.id not in behoud_ids]
    return {"categorieen": cats, "kanalen": chans}

async def voer_shutdown_uit(interaction):
    guild = interaction.guild
    mededeling = guild.get_channel(MEDEDELING_KANAAL_ID)
    behoud = {mededeling.id, mededeling.category_id} if mededeling else set()
    snapshot = maak_snapshot(guild, behoud)
    STATE_BESTAND.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    if mededeling:
        await mededeling.send("@everyone", embed=discord.Embed(title="🔴 Server gesloten", color=0xED4245))
    for ch in guild.channels:
        if ch.id not in behoud and not isinstance(ch, discord.CategoryChannel):
            try:
                await ch.delete()
            except Exception:
                pass
    await interaction.edit_original_response(content="✅ Shutdown voltooid.", view=None)

class BevestigShutdown(ui.View):
    def __init__(self, uid): super().__init__(timeout=60); self.uid = uid
    @ui.button(label="Ja", style=discord.ButtonStyle.danger)
    async def ja(self, i: discord.Interaction, b: ui.Button):
        if i.user.id != self.uid: return
        await i.response.edit_message(content="⏳ Bezig...", view=None)
        await voer_shutdown_uit(i)

class FinnsBot(commands.Bot):
    def __init__(self): super().__init__(command_prefix="!", intents=discord.Intents.all())

    async def setup_hook(self):
        self.add_view(VerificationView())
        self.add_view(TicketKnop())
        self.add_view(SluitKnop())
        self.add_view(ShopView())
        self.add_view(BetaalStartView())
        self.add_view(GiveawayView())

        try:
            self.tree.clear_commands(guild=None)
            await self.tree.sync(guild=None)
            guild_obj = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            print(f"✅ Schone commando's gesynchroniseerd ({len(synced)} stuks).")
        except Exception as e:
            print(f"⚠️ Fout bij sync: {e}")
        
        check_twee_wekelijkse_overzicht.start()

bot = FinnsBot()

@tasks.loop(hours=1)
async def check_twee_wekelijkse_overzicht():
    nu = datetime.now(timezone.utc)
    if nu.weekday() == 6 and nu.hour == 12 and (nu.isocalendar().week % 2 == 0):
        kanaal = bot.get_channel(WEEK_OVERZICHT_KANAAL_ID)
        if kanaal:
            guild = bot.get_guild(GUILD_ID)
            totaal_leden = guild.member_count if guild else "Onbekend"
            e = discord.Embed(title="📊 Twee-wekelijks Server Overzicht", color=KLEUR, timestamp=nu)
            e.add_field(name="👋 Nieuwe Leden", value=f"**{WEEK_STATS['joins']}**", inline=True)
            e.add_field(name="✅ Geverifieerd", value=f"**{WEEK_STATS['verificaties']}**", inline=True)
            e.add_field(name="👥 Totaal Leden", value=f"**{totaal_leden}**", inline=True)
            e.add_field(name="🛒 Nieuwe Bestellingen", value=f"**{WEEK_STATS['nieuwe_bestellingen']}**", inline=True)
            e.add_field(name="🎉 Afgerond", value=f"**{WEEK_STATS['afgeronde_bestellingen']}**", inline=True)
            await kanaal.send(embed=e)
            WEEK_STATS.update({"joins": 0, "verificaties": 0, "nieuwe_bestellingen": 0, "afgeronde_bestellingen": 0})
            bewaar_stats(WEEK_STATS)

@bot.event
async def on_ready():
    print(f"🤖 Ingelogd als {bot.user}")

@bot.event
async def on_member_join(member: discord.Member):
    WEEK_STATS["joins"] += 1
    bewaar_stats(WEEK_STATS)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    if isinstance(message.channel, discord.DMChannel):
        user_id = message.author.id
        if user_id in pending_pay_submissions:
            data = pending_pay_submissions[user_id]
            if data.get("status") == "SETUP":
                if message.attachments:
                    data["image_url"] = message.attachments[0].url
                    await message.channel.send("📸 Afbeelding ontvangen! Klik op 'Afbeelding verstuurd'.")
                elif message.content:
                    data["product"] = message.content
                    await message.channel.send("📝 Productnaam opgeslagen! Klik op 'Bericht indienen'.")
            elif data.get("status") == "AWAITING_PAYMENT":
                if message.content.strip().lower() == "betaald":
                    confirm_channel = bot.get_channel(CHANNEL_BETAAL_CONFIRM)
                    if confirm_channel:
                        e = discord.Embed(title="💸 Betaling Gemeld", description=f"**Klant:** {message.author.mention}", color=discord.Color.gold())
                        if data.get("image_url"): e.set_thumbnail(url=data["image_url"])
                        await confirm_channel.send(embed=e, view=BetaalConfirmView(message.author))
                        await message.channel.send("✅ Betaling doorgezonden naar het team!")
                        data["status"] = "VERIFYING_PAYMENT"
        return
    await bot.process_commands(message)

# ALLE COMMANDS:
@bot.tree.command(name="help", description="Laat alle commands zien")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=help_embed(is_staff(interaction.user)), ephemeral=True)

@bot.tree.command(name="giveaway", description="Start een winactie")
async def giveaway_cmd(interaction: discord.Interaction, prijs: str, duur: str, winnaars: int = 1):
    if not await staff_check(interaction): return
    sec = verwerk_tijd(duur)
    if not sec:
        await interaction.response.send_message("❌ Ongeldige tijd!", ephemeral=True)
        return
    v = GiveawayView()
    eind = datetime.now(timezone.utc) + timedelta(seconds=sec)
    e = embed("🎉 GIVEAWAY!", f"**Prijs:** {prijs}\n**Winnaars:** {winnaars}\n**Eindigt:** <t:{int(eind.timestamp())}:R>")
    await interaction.response.send_message("✅ Giveaway gestart!", ephemeral=True)
    msg = await interaction.channel.send(embed=e, view=v)
    await asyncio.sleep(sec)
    for child in v.children: child.disabled = True
    if not v.deelnemers:
        await msg.edit(content="❌ Geen deelnemers.", view=v)
    else:
        gekosen = random.sample(list(v.deelnemers), min(len(v.deelnemers), winnaars))
        w_txt = ", ".join([f"<@{uid}>" for uid in gekosen])
        await msg.edit(embed=embed("🎉 AFGELOPEN", f"**Prijs:** {prijs}\n**Winnaars:** {w_txt}"), view=v)
        await interaction.channel.send(f"🎉 Gefeliciteerd {w_txt}!")

@bot.tree.command(name="betaalticket", description="Plaats het betaalpanel")
async def betaalticket_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction): return
    await interaction.channel.send(embed=discord.Embed(title="💳 Betaal Aanvragen", color=discord.Color.green()), view=BetaalStartView())
    await interaction.response.send_message("✅ Betaalpanel geplaatst!", ephemeral=True)

@bot.tree.command(name="bots", description="Bekijk de bots")
async def bots_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=bots_embed(), ephemeral=True)

@bot.tree.command(name="prijzen", description="Prijslijst")
async def prijzen_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=prijzen_embed(), ephemeral=True)

@bot.tree.command(name="shop", description="Open de winkel")
async def shop_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=bots_embed(), view=ShopView(), ephemeral=True)

@bot.tree.command(name="bestellen", description="Bestel een product")
@app_commands.autocomplete(product=product_autocomplete)
async def bestellen_cmd(interaction: discord.Interaction, product: str = None, code: str = None):
    gekozen = vind_product(product) if product else None
    await maak_ticket(interaction, gekozen, code)

@bot.tree.command(name="kortingscodegebruik", description="Check kortingscode")
async def kortingscodegebruik_cmd(interaction: discord.Interaction, code: str):
    sleutel = code.strip().upper()
    if sleutel in SHOP["kortingscodes"]:
        await interaction.response.send_message(f"🎉 Code `{sleutel}` geeft {SHOP['kortingscodes'][sleutel]}% korting.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Code `{sleutel}` is ongeldig.", ephemeral=True)

@bot.tree.command(name="mijnbestellingen", description="Jouw bestellingen")
async def mijnbestellingen_cmd(interaction: discord.Interaction):
    mijn = [b for b in SHOP["bestellingen"] if b["gebruiker_id"] == interaction.user.id]
    if not mijn:
        await interaction.response.send_message("Je hebt nog niets besteld.", ephemeral=True)
        return
    e = embed("📦 Jouw Bestellingen")
    for b in mijn[-10:]:
        e.add_field(name=f"#{b['id']} {b['product_naam']}", value=f"{euro(b['prijs'])} • {b['status']}", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="review", description="Laat een review achter")
async def review_cmd(interaction: discord.Interaction, sterren: app_commands.Range[int, 1, 5], tekst: str):
    kanaal = interaction.guild.get_channel(KANAAL_REVIEWS_ID)
    if not kanaal:
        await interaction.response.send_message("Review-kanaal niet gevonden.", ephemeral=True)
        return
    e = discord.Embed(title="⭐" * sterren, description=tekst, color=0xFEE75C)
    e.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
    await kanaal.send(embed=e)
    await interaction.response.send_message("Bedankt voor je review!", ephemeral=True)

@bot.tree.command(name="serverinfo", description="Server info")
async def serverinfo_cmd(interaction: discord.Interaction):
    g = interaction.guild
    e = embed(f"ℹ️ {g.name}", f"Leden: {g.member_count}")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="ping", description="Snelheidstest")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)} ms", ephemeral=True)

@bot.tree.command(name="berichtbot", description="Stuur bericht als bot")
async def berichtbot_cmd(interaction: discord.Interaction, bericht: str, afbeelding: discord.Attachment = None):
    if not await staff_check(interaction): return
    bestand = await afbeelding.to_file() if afbeelding else None
    await interaction.channel.send(content=bericht, file=bestand)
    await interaction.response.send_message("✅ Verzonden!", ephemeral=True)

@bot.tree.command(name="product_toevoegen", description="Voeg product toe")
async def product_toevoegen_cmd(interaction: discord.Interaction, naam: str, omschrijving: str, prijs: float):
    if not await staff_check(interaction): return
    p = {"id": SHOP["volgend_product"], "naam": naam, "omschrijving": omschrijving, "prijs": round(prijs, 2)}
    SHOP["volgend_product"] += 1
    SHOP["producten"].append(p)
    bewaar_shop()
    await interaction.response.send_message("✅ Product toegevoegd!", embed=product_embed(p), ephemeral=True)

@bot.tree.command(name="product_bewerken", description="Bewerk product")
@app_commands.autocomplete(product=product_autocomplete)
async def product_bewerken_cmd(interaction: discord.Interaction, product: str, nieuwe_naam: str = None, omschrijving: str = None, prijs: float = None):
    if not await staff_check(interaction): return
    p = vind_product(product)
    if not p:
        await interaction.response.send_message("Niet gevonden.", ephemeral=True)
        return
    if nieuwe_naam: p["naam"] = nieuwe_naam
    if omschrijving: p["omschrijving"] = omschrijving
    if prijs: p["prijs"] = round(prijs, 2)
    bewaar_shop()
    await interaction.response.send_message("✅ Aangepast!", embed=product_embed(p), ephemeral=True)

@bot.tree.command(name="product_verwijderen", description="Verwijder product")
@app_commands.autocomplete(product=product_autocomplete)
async def product_verwijderen_cmd(interaction: discord.Interaction, product: str):
    if not await staff_check(interaction): return
    p = vind_product(product)
    if not p:
        await interaction.response.send_message("Niet gevonden.", ephemeral=True)
        return
    SHOP["producten"].remove(p)
    bewaar_shop()
    await interaction.response.send_message(f"🗑️ Verwijderd.", ephemeral=True)

@bot.tree.command(name="bestellingen", description="Open bestellingen")
async def bestellingen_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction): return
    open_b = [b for b in SHOP["bestellingen"] if b["status"] == "open"]
    if not open_b:
        await interaction.response.send_message("Geen open bestellingen.", ephemeral=True)
        return
    e = embed("🟡 Open Bestellingen")
    for b in open_b[:25]:
        e.add_field(name=f"#{b['id']} {b['product_naam']}", value=f"<@{b['gebruiker_id']}> • {euro(b['prijs'])}", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="afronden", description="Rond bestelling af")
async def afronden_cmd(interaction: discord.Interaction, bestelling_id: int):
    if not await staff_check(interaction): return
    await interaction.response.defer(ephemeral=True)
    b = vind_bestelling(bestelling_id)
    if not b or b["status"] != "open":
        await interaction.followup.send("Bestelling niet gevonden of al gesloten.", ephemeral=True)
        return
    b["status"] = "afgerond"
    bewaar_shop()
    WEEK_STATS["afgeronde_bestellingen"] += 1
    bewaar_stats(WEEK_STATS)
    await log_bestelling(interaction.guild, bestelling_embed(b, f"✅ Bestelling #{b['id']} afgerond"))
    await interaction.followup.send(f"✅ Bestelling #{b['id']} afgerond.", ephemeral=True)

@bot.tree.command(name="annuleren", description="Annuleer bestelling")
async def annuleren_cmd(interaction: discord.Interaction, bestelling_id: int):
    b = vind_bestelling(bestelling_id)
    if not b or not (is_staff(interaction.user) or b["gebruiker_id"] == interaction.user.id):
        await interaction.response.send_message("Geen toegang of niet gevonden.", ephemeral=True)
        return
    b["status"] = "geannuleerd"
    bewaar_shop()
    await interaction.response.send_message(f"🔴 Bestelling #{b['id']} geannuleerd.", ephemeral=True)

@bot.tree.command(name="kortingscode_maken", description="Maak kortingscode")
async def kortingscode_maken_cmd(interaction: discord.Interaction, code: str, procent: int):
    if not await staff_check(interaction): return
    SHOP["kortingscodes"][code.strip().upper()] = procent
    bewaar_shop()
    await interaction.response.send_message(f"✅ Code `{code}` aangemaakt ({procent}%).", ephemeral=True)

@bot.tree.command(name="kortingscode_verwijderen", description="Verwijder code")
async def kortingscode_verwijderen_cmd(interaction: discord.Interaction, code: str):
    if not await staff_check(interaction): return
    if SHOP["kortingscodes"].pop(code.strip().upper(), None) is None:
        await interaction.response.send_message("Code bestaat niet.", ephemeral=True)
        return
    bewaar_shop()
    await interaction.response.send_message("🗑️ Verwijderd.", ephemeral=True)

@bot.tree.command(name="shopstats", description="Shop statistieken")
async def shopstats_cmd(interaction: discord.Interaction):
    if not await staff_check(interaction): return
    alle = SHOP["bestellingen"]
    omzet = sum(b["prijs"] for b in alle if b["status"] == "afgerond")
    e = embed("📊 Shop Statistieken", f"Totale omzet: {euro(omzet)}")
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="ban", description="Ban een gebruiker")
@app_commands.checks.has_permissions(ban_members=True)
async def ban_command(interaction: discord.Interaction, member: discord.Member, reason: str = "Geen reden"):
    await interaction.response.defer(ephemeral=True)
    await member.ban(reason=reason)
    await interaction.followup.send(f"Gebruiker {member.mention} is gebanned.", ephemeral=True)

@bot.tree.command(name="kick", description="Kick een gebruiker")
@app_commands.checks.has_permissions(kick_members=True)
async def kick_command(interaction: discord.Interaction, member: discord.Member, reason: str = "Geen reden"):
    await interaction.response.defer(ephemeral=True)
    await member.kick(reason=reason)
    await interaction.followup.send(f"Gebruiker {member.mention} is gekicked.", ephemeral=True)

@bot.tree.command(name="clear", description="Verwijder berichten")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear_command(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"✅ {len(deleted)} berichten verwijderd.", ephemeral=True)

bot.run(TOKEN)
