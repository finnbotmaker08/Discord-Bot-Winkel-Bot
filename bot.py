from datetime import datetime, timedelta, timezone
import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Laad de .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("❌ Fout: Geen DISCORD_TOKEN gevonden in het .env bestand!")
    exit(1)

# Haal overige variabelen op uit .env (met veilige fallbacks)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID")) if os.getenv("LOG_CHANNEL_ID") else 1556597111410130954
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID")) if os.getenv("TICKET_CATEGORY_ID") else 1556576202880319518
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID")) if os.getenv("MOD_ROLE_ID") else 1556578108608487484
SHOP_ROLE_ID = int(os.getenv("SHOP_ROLE_ID")) if os.getenv("SHOP_ROLE_ID") else 1556578814086217778

# --- CONFIGURATIE BETALINGEN & ROLLEN ---
PAID_CHANNEL_ID = 1556576438688153721

ROLE_BASIC = 1556578626005377076
ROLE_NORMAAL = 1556578625640333332
ROLE_PREMIUM = 1556578625019449425

# Intents instellen
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class ShopAndPartnerBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Registreer persistente views zodat knoppen blijven werken na een herstart
        self.add_view(TicketView())
        self.add_view(TicketSluitView())
        self.add_view(PartnerStartView())
        
        await self.tree.sync()
        print("✅ Slash commands succesvol gesynchroniseerd.")

bot = ShopAndPartnerBot()
tree = bot.tree

# --- CONFIGURATIE PARTNER SYSTEEM ---
ROLE_ACCEPTEREN = 1554525725657145354
ROLE_PARTNER_BEHEER = 1541819580173779026
ROLE_EXTRA_ACCEPTEREN = 1545038388091166790
ROLE_NIEUW_PARTNER = 1556578093081305159  # Jouw nieuwe rol

OWNER_IDS = [1328766617164972115, 1305271257901695048]

CHANNEL_AANVRAAG = 1555910106040762408
CHANNEL_PARTNER_PUBLIC = 1476292683508089056
CHANNEL_PARTNER_PANEL = 1542844065702350878
CHANNEL_LOGS = LOG_CHANNEL_ID

pending_partner_submissions = {}  # user_id -> image_url
pending_partner_messages = {}     # user_id -> partner bericht tekst
partner_cooldowns = {}            # user_id -> datetime van laatste aanvraag

# Jouw aangepaste partnerbericht
EXACT_PARTNER_BERICHT = (
    "# Discord Bot Winkel\n\n"
    "🚀 Upgrade jouw server slimmer, niet duurder!\n\n"
    "Wil jij jouw Discord-server professionaliseren met topkwaliteit bots, maar weiger je de hoofdprijs te betalen? Stop met zoeken. Bij Discord Tools Winkel scoor je professionele bots en tools voor een fractie van de normale prijs.\n\n"
    "Wat jij krijgt:\n\n"
    "💎 Premium kwaliteit voor een budgetvriendelijk prijsje\n\n"
    "⚡ Snelle setup en betrouwbare werking\n\n"
    "📈 Direct meer beleving en professionaliteit in je server\n\n"
    "Mis deze deal niet en neem direct een kijkje in onze winkel:\n"
    "🔗 Join nu: https://discord.gg/mqXxAVGnZ\n\n"
    "**Nu 20% korting!**"
)


# --- PERSISTENTE VIEWS VOOR TICKETS ---

class TicketSluitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Sluit Ticket", style=discord.ButtonStyle.danger, custom_id="sluit_ticket_knop")
    async def sluit_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Dit ticket wordt over 5 seconden gesloten en verwijderd...", ephemeral=False)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.Forbidden:
            await interaction.channel.send("❌ Ik heb geen rechten om dit kanaal te verwijderen!")

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Open een Ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket_knop")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        
        bestaand_kanaal = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if bestaand_kanaal:
            await interaction.response.send_message(f"❌ Je hebt al een open ticket: {bestaand_kanaal.mention}", ephemeral=True)
            return

        category = None
        if TICKET_CATEGORY_ID:
            cat_obj = guild.get_channel(TICKET_CATEGORY_ID)
            if isinstance(cat_obj, discord.CategoryChannel):
                category = cat_obj

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        if MOD_ROLE_ID:
            mod_role = guild.get_role(MOD_ROLE_ID)
            if mod_role:
                overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            ticket_kanaal = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket van {interaction.user} (ID: {interaction.user.id})"
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Kon geen kanaal aanmaken. Zorg dat `TICKET_CATEGORY_ID` in je .env een geldige Categorie-ID is! (Fout: {e})", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎫 Ondersteuning & Bestellingen",
            description=f"Welkom {interaction.user.mention}!\n\n"
                        "Vertel hieronder welk pakket je wilt of waar je hulp bij nodig hebt. "
                        "De staff komt je zo snel mogelijk helpen!\n\n"
                        "Klik op de knop hieronder om het ticket te sluiten wanneer het is opgelost.",
            color=discord.Color.blue()
        )
        await ticket_kanaal.send(content=interaction.user.mention, embed=embed, view=TicketSluitView())
        await interaction.response.send_message(f"✅ Je ticket is aangemaakt: {ticket_kanaal.mention}!", ephemeral=True)


# --- PERSISTENTE VIEWS VOOR PARTNERS ---

class DenyReasonModal(discord.ui.Modal, title="Partner Aanvraag Afkeuren"):
    reden = discord.ui.TextInput(
        label="Reden van afkeuring",
        style=discord.TextStyle.paragraph,
        placeholder="Geef hier de reden op waarom de aanvraag wordt afgekeurd...",
        required=True
    )

    def __init__(self, member: discord.Member, original_message: discord.Message, view_instance: discord.ui.View):
        super().__init__()
        self.member = member
        self.original_message = original_message
        self.view_instance = view_instance

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        for child in self.view_instance.children:
            child.disabled = True
        try:
            await self.original_message.edit(view=self.view_instance)
        except Exception:
            pass

        try:
            await self.member.send(f"❌ Jouw partner-aanvraag is helaas **afgekeurd**.\n**Reden:** {self.reden.value}")
        except discord.Forbidden:
            pass

        user_partner_msg = pending_partner_messages.get(self.member.id, "Geen partner bericht opgegeven.")

        guild = interaction.guild or (bot.guilds[0] if bot.guilds else None)
        if guild:
            log_kanaal = guild.get_channel(CHANNEL_LOGS)
            if log_kanaal:
                embed_log = discord.Embed(
                    title="❌ Partner Aanvraag Afgekeurd Log",
                    description=(
                        f"**Aanvrager:** {self.member.mention} (`{self.member.id}`)\n"
                        f"**Afgekeurd door:** {interaction.user.mention} (`{interaction.user.id}`)\n\n"
                        f"**Ingevoerde Partner Bericht:**\n{user_partner_msg}\n\n"
                        f"**Reden van afkeuring:** {self.reden.value}"
                    ),
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                try:
                    await log_kanaal.send(embed=embed_log)
                except Exception as e:
                    print(f"Fout bij versturen log (afwijzen): {e}")

        pending_partner_submissions.pop(self.member.id, None)
        pending_partner_messages.pop(self.member.id, None)

        await interaction.followup.send(f"Aanvraag van {self.member.mention} is afgekeurd met reden: {self.reden.value}", ephemeral=True)


class PartnerReviewView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=None)
        self.member = member

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in OWNER_IDS:
            return True
        role_ids = [role.id for role in interaction.user.roles]
        toegestane_rollen = [ROLE_ACCEPTEREN, ROLE_EXTRA_ACCEPTEREN, ROLE_NIEUW_PARTNER]
        if not any(r_id in role_ids for r_id in toegestane_rollen):
            await interaction.response.send_message("Jij hebt geen toestemming om dit te beoordelen.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accepteren", style=discord.ButtonStyle.green, custom_id="partner_accept_btn")
    async def accept_partner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild or (bot.guilds[0] if bot.guilds else None)

        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        try:
            await self.member.send("✅ Jouw partner-aanvraag is **geaccepteerd**!")
        except discord.Forbidden:
            pass

        partner_kanaal = guild.get_channel(CHANNEL_PARTNER_PUBLIC)
        if not partner_kanaal:
            await interaction.followup.send(f"❌ Fout: Partner kanaal met ID `{CHANNEL_PARTNER_PUBLIC}` niet gevonden!", ephemeral=True)
            return

        user_partner_msg = pending_partner_messages.get(self.member.id, "Geen partner bericht opgegeven.")
        
        try:
            await partner_kanaal.send(content=user_partner_msg)
        except Exception as e:
            await interaction.followup.send(f"❌ Kon geen bericht plaatsen in het partnerkanaal: {e}", ephemeral=True)
            return

        log_kanaal = guild.get_channel(CHANNEL_LOGS)
        if log_kanaal:
            embed_log = discord.Embed(
                title="✅ Partner Aanvraag Geaccepteerd Log",
                description=(
                    f"**Aanvrager:** {self.member.mention} (`{self.member.id}`)\n"
                    f"**Geaccepteerd door:** {interaction.user.mention} (`{interaction.user.id}`)\n\n"
                    f"**Geplaatst Partner Bericht:**\n{user_partner_msg}"
                ),
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            try:
                await log_kanaal.send(embed=embed_log)
            except Exception as e:
                print(f"Fout bij versturen log (accepteren): {e}")
        
        pending_partner_submissions.pop(self.member.id, None)
        pending_partner_messages.pop(self.member.id, None)

        await interaction.followup.send(f"Aanvraag van {self.member.mention} is succesvol geaccepteerd en geplaatst in het partnerkanaal!", ephemeral=True)

    @discord.ui.button(label="Afkeuren", style=discord.ButtonStyle.red, custom_id="partner_deny_btn")
    async def deny_partner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DenyReasonModal(self.member, interaction.message, self))


class PartnerMsgSubmitView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Partner bericht versturen", style=discord.ButtonStyle.green, emoji="📤", custom_id="partner_msg_done_btn")
    async def msg_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        user_partner_msg = pending_partner_messages.get(self.user_id)
        if not user_partner_msg:
            await interaction.followup.send("Je hebt nog geen partner bericht ingevoerd in deze DM! Stuur eerst de tekst van jouw partner bericht.", ephemeral=True)
            return

        guild = bot.guilds[0] if bot.guilds else None
        if not guild:
            await interaction.followup.send("Kan geen verbinding maken met de server.", ephemeral=True)
            return

        aanvraag_kanaal = guild.get_channel(CHANNEL_AANVRAAG)
        if not aanvraag_kanaal:
            await interaction.followup.send("Het aanvraagkanaal kon niet worden gevonden op de server.", ephemeral=True)
            return

        image_url = pending_partner_submissions.get(self.user_id)

        try:
            embed = discord.Embed(
                title="🤝 Nieuwe Partner Aanvraag",
                description=f"**Gebruiker:** {interaction.user.mention} (`{interaction.user.id}`)\n\n**Ingevoerde Partner Bericht van gebruiker:**\n{user_partner_msg}\n\n**Ingezonden Bewijs (Screenshot):**",
                color=discord.Color.blue()
            )
            if image_url:
                embed.set_image(url=image_url)

            await aanvraag_kanaal.send(embed=embed, view=PartnerReviewView(interaction.user))
        except Exception as e:
            await interaction.followup.send(f"Er ging iets mis bij het versturen naar het kanaal: {e}", ephemeral=True)
            return

        try:
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
        except Exception:
            pass

        await interaction.followup.send("Uw partner-aanvraag is succesvol ingediend en wordt zo spoedig mogelijk bekeken.", ephemeral=True)


class PartnerImageView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Foto verstuurd", style=discord.ButtonStyle.blurple, emoji="📸", custom_id="partner_image_sent_btn")
    async def image_sent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if self.user_id not in pending_partner_submissions:
            await interaction.followup.send("Je hebt nog geen foto / screenshot ingestuurd in deze DM!", ephemeral=True)
            return

        try:
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
        except Exception:
            pass

        try:
            await interaction.user.send(
                content=(
                    "⚠️ **LET OP! MAAK JE PARTNER BERICHT NIET LANGER DAN 2000 WOORDEN! ZO WEL WORD U AFGEKEURD!**\n\n"
                    "📝 **Stap 3: Geef uw partner bericht aan ons.**\n"
                    "Typ en stuur nu jouw partner bericht in deze DM en klik daarna op de knop hieronder om de aanvraag definitief te verzenden."
                ),
                view=PartnerMsgSubmitView(self.user_id)
            )
        except discord.Forbidden:
            pass


class PartnerSendMsgView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Bericht verstuurd", style=discord.ButtonStyle.green, emoji="📤", custom_id="partner_msg_sent_btn")
    async def msg_sent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        try:
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
        except Exception:
            pass

        try:
            await interaction.user.send(
                content="📸 **Stap 2: Foto indienen**\nStuur nu een screenshot (afbeelding) als bewijs dat het bericht in jouw server staat in deze DM en klik daarna op de knop hieronder.",
                view=PartnerImageView(self.user_id)
            )
        except discord.Forbidden:
            pass


class MemberCheckView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Ja, ik voldoe hieraan (15+ leden)", style=discord.ButtonStyle.green, custom_id="member_check_yes")
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        try:
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
        except Exception:
            pass

        try:
            await interaction.user.send(
                content=f"**Stap 1: Partner Bericht Plaatsen**\nDien uw partner bericht nu in, als u dat gedaan heeft klik dan op de knop: Bericht verstuurd\n\n{EXACT_PARTNER_BERICHT}",
                view=PartnerSendMsgView(self.user_id)
            )
            await interaction.followup.send("Ik heb je een privébericht (DM) gestuurd met verdere instructies!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Ik kon je geen DM sturen. Zorg ervoor dat je privéberichten open staan!", ephemeral=True)

    @discord.ui.button(label="Nee", style=discord.ButtonStyle.red, custom_id="member_check_no")
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
        except Exception:
            pass
        partner_cooldowns.pop(self.user_id, None)
        await interaction.followup.send("❌ Je voldoet niet aan de eis van 15+ leden. Het proces is geannuleerd.", ephemeral=True)


class PartnerStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start Partner Aanvraag", style=discord.ButtonStyle.green, custom_id="partner_start_btn")
    async def start_partner_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        now = datetime.now(timezone.utc)

        if user_id in partner_cooldowns:
            laatste_tijd = partner_cooldowns[user_id]
            verschil = now - laatste_tijd
            if verschil < timedelta(hours=12):
                overgebleven = timedelta(hours=12) - verschil
                uren = int(overgebleven.total_seconds() // 3600)
                minuten = int((overgebleven.total_seconds() % 3600) // 60)
                await interaction.followup.send(
                    f"⏳ Je kunt dit maximaal 1 keer per 12 uur doen. Probeer het over **{uren} uur en {minuten} minuten** opnieuw.",
                    ephemeral=True
                )
                return

        partner_cooldowns[user_id] = now

        try:
            dm_channel = await interaction.user.create_dm()
            await dm_channel.send(
                content="Voldoet jouw server aan de eis van **minimaal 15 leden**?",
                view=MemberCheckView(user_id)
            )
            await interaction.followup.send("Ik heb je een privébericht (DM) gestuurd om de controle te starten!", ephemeral=True)
        except discord.Forbidden:
            partner_cooldowns.pop(user_id, None)
            await interaction.followup.send("❌ Ik kon je geen DM sturen. Zorg ervoor dat je **privéberichten (DM's)** open staan voor leden van deze server!", ephemeral=True)


# --- BOT EVENTS ---

@bot.event
async def on_ready():
    print(f"🤖 Ingelogd als {bot.user} (ID: {bot.user.id})")
    print("-----------------------------------------")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        user_id = message.author.id
        
        if message.attachments:
            pending_partner_submissions[user_id] = message.attachments[0].url
            await message.channel.send("📸 Foto succesvol ontvangen! Klik nu op de knop **'Foto verstuurd'** in het vorige bericht om door te gaan naar Stap 3.")
        
        elif message.content and user_id in pending_partner_submissions and user_id not in pending_partner_messages:
            pending_partner_messages[user_id] = message.content
            await message.channel.send("📝 Partner bericht succesvol ontvangen! Klik nu op de knop **'Partner bericht versturen'** om de aanvraag definitief in te dienen.")

    await bot.process_commands(message)


# --- SLASH COMMANDO'S: SHOP & TICKET ---

@tree.command(name="ticketpanel", description="Stuur het ticket-paneel naar dit kanaal")
@app_commands.checks.has_permissions(manage_channels=True)
async def ticketpanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛒 Hulp Nodig of een Bot Kopen?",
        description="Klik op de knop hieronder om direct een privé-ticket te openen met ons team. We helpen je graag verder!",
        color=discord.Color.blurple()
    )
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Ticketpaneel succesvol verzonden!", ephemeral=True)


@tree.command(name="buy", description="Bestel een bot en ontvang direct je betaallink!")
@app_commands.describe(pakket="Kies uit het basic, normaal of premium pakket")
@app_commands.choices(pakket=[
    app_commands.Choice(name="Basic (€7,00)", value="basic"),
    app_commands.Choice(name="Normaal (€15,00)", value="normaal"),
    app_commands.Choice(name="Premium (€27,00)", value="premium")
])
async def buy(interaction: discord.Interaction, pakket: str):
    pakket_info = {
        "basic": {
            "naam": "Basic (€7,00)",
            "details": "• 2 maanden\n• Geen 24/7\n• 6 custom commands",
            "tekst": "Wil je mij alsjeblieft € 7,00 betalen voor 'De bot wordgeleverdzondergarantie' via https://tikkie.me/pay/7ml7iv7ilta0d643kdnt\n\nDeze link is geldig t/m 19 oktober"
        },
        "normaal": {
            "naam": "Normaal (€15,00)",
            "details": "• 5 maanden\n• Met 24/7 Running\n• 12 custom commands",
            "tekst": "Wil je mij alsjeblieft € 15,00 betalen voor 'De bot wordgeleverdzondergarantie' via https://tikkie.me/pay/1m1tjn0il8apml1hnqv4\n\nDeze link is geldig t/m 19 oktober"
        },
        "premium": {
            "naam": "Premium (€27,00)",
            "details": "• 1,5 jaar\n• Met 24/7 Running\n• 20 custom commands\n• Onderhoud inbegrepen",
            "tekst": "Wil je mij alsjeblieft € 27,00 betalen voor 'De bot wordgeleverdzondergarantie' via https://tikkie.me/pay/tkila65ee402867mbg33\n\nDeze link is geldig t/m 19 oktober"
        }
    }

    info = pakket_info[pakket]

    try:
        embed_dm = discord.Embed(
            title=f"🛒 Jouw Bestelling: {info['naam']}",
            description=f"Bedankt voor je interesse!\n\n**Inhoud pakket:**\n{info['details']}\n\n**Betaalinstructie:**\n{info['tekst']}",
            color=discord.Color.green()
        )
        await interaction.user.send(embed=embed_dm)
        dm_verzonden = True
    except discord.Forbidden:
        dm_verzonden = False

    if LOG_CHANNEL_ID:
        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed_log = discord.Embed(
                title="🚨 Nieuwe Bot Bestelling (/buy)!",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed_log.add_field(name="Klant", value=f"{interaction.user.mention} (`{interaction.user}`)", inline=False)
            embed_log.add_field(name="Gekozen pakket", value=info['naam'], inline=False)
            embed_log.add_field(name="Betaallink gestuurd", value=info['tekst'], inline=False)
            embed_log.set_footer(text=f"Gebruiker ID: {interaction.user.id}")
            await log_channel.send(embed=embed_log)

    bericht = f"Bedankt voor je bestelling, {interaction.user.mention}! 🎉"
    if dm_verzonden:
        bericht += " Ik heb je een privébericht (DM) gestuurd met de betaallink en informatie!"
    else:
        bericht += " (Zet je DM's open zodat we je de betaallink kunnen sturen, of open even een ticket!)"

    await interaction.response.send_message(bericht, ephemeral=True)


@tree.command(name="betaald", description="Registreer dat een klant heeft betaald, geef automatisch de rol en stuur log (Staff)")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(
    klant="De klant die betaald heeft",
    pakket="Kies het pakket dat de klant heeft gekocht"
)
@app_commands.choices(pakket=[
    app_commands.Choice(name="Basic", value="basic"),
    app_commands.Choice(name="Normaal", value="normaal"),
    app_commands.Choice(name="Premium", value="premium")
])
async def betaald(interaction: discord.Interaction, klant: discord.Member, pakket: str):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    role_id_map = {
        "basic": (ROLE_BASIC, "Basic (€7,00)"),
        "normaal": (ROLE_NORMAAL, "Normaal (€15,00)"),
        "premium": (ROLE_PREMIUM, "Premium (€27,00)")
    }

    target_role_id, pakket_naam = role_id_map[pakket]
    role = guild.get_role(target_role_id)

    if not role:
        await interaction.followup.send(f"❌ Fout: De rol voor `{pakket_naam}` kon niet worden gevonden op basis van het ID!", ephemeral=True)
        return

    # Rol toekennen aan de klant
    try:
        await klant.add_roles(role, reason=f"Betaling bevestigd door {interaction.user}")
    except discord.Forbidden:
        await interaction.followup.send("❌ Ik heb onvoldoende rechten om deze rol aan de gebruiker toe te kennen! Controleer de rolhiërarchie.", ephemeral=True)
        return

    # Bericht sturen naar het betaalde kanaal (1556576438688153721)
    paid_channel = guild.get_channel(PAID_CHANNEL_ID)
    if paid_channel:
        embed_paid = discord.Embed(
            title="🎉 Nieuwe Betaling Bevestigd!",
            description=f"Bedankt voor je aankoop, {klant.mention}!\n\n"
                        f"📦 **Pakket:** {pakket_naam}\n"
                        f"🛡 **Toegekende Rol:** {role.mention}\n"
                        f"👤 **Gecontroleerd door:** {interaction.user.mention}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed_paid.set_footer(text=f"Klant ID: {klant.id}")
        await paid_channel.send(content=klant.mention, embed=embed_paid)
    else:
        await interaction.followup.send(f"⚠️ Betaling verwerkt en rol toegekend, maar betaalkanaal (`{PAID_CHANNEL_ID}`) kon niet worden gevonden!", ephemeral=True)
        return

    await interaction.followup.send(f"✅ Betaling succesvol geregistreerd! {klant.mention} heeft de rol **{role.name}** gekregen en er is een melding geplaatst in <#{PAID_CHANNEL_ID}>.", ephemeral=True)


@tree.command(name="tools", description="Bekijk de beschikbare bot-pakketten en info")
async def tools(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Onze Bot Pakketten",
        description="Bekijk hieronder onze opties en bestel direct via `/buy` of open een ticket!",
        color=discord.Color.dark_theme()
    )
    embed.add_field(name="📦 Basic (€7,-)", value="• 2 maanden\n• Bot ZONDER 24/7\n• 6 custom commands", inline=False)
    embed.add_field(name="🚀 Normaal (€15,-)", value="• 5 maanden\n• Bot Met 24/7 Running\n• 12 custom commands", inline=False)
    embed.add_field(name="👑 Premium (€27,-)", value="• 1,5 jaar\n• Bot Met 24/7 Running\n• 20 custom commands\n• Onderhoud inbegrepen (maak ticket aan)", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=False)


@tree.command(name="prijzen", description="Bekijk de prijzenlijst van de shop")
async def prijzen(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🏷 Prijzenlijst",
        description="Transparante prijzen voor al onze diensten en bots:",
        color=discord.Color.gold()
    )
    embed.add_field(name="📦 Basic Pakket", value="**€7,-**\n• 2 maanden\n• ZONDER 24/7\n• 6 custom commands", inline=False)
    embed.add_field(name="🚀 Normaal Pakket", value="**€15,-**\n• 5 maanden\n• Met 24/7 Running\n• 12 custom commands", inline=False)
    embed.add_field(name="👑 Premium Pakket", value="**€27,-**\n• 1,5 jaar\n• Met 24/7 Running\n• 20 custom commands\n• Onderhoud inbegrepen", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=False)


@tree.command(name="voorraad", description="Bekijk de actuele voorraad van de shop")
async def voorraad(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📦 Actuele Shop Voorraad",
        description="Hier is een overzicht van wat er momenteel beschikbaar is:",
        color=discord.Color.green()
    )
    embed.add_field(name="📦 Basic Bot", value="✅ **Op voorraad**", inline=False)
    embed.add_field(name="🚀 Normaal Bot", value="✅ **Op voorraad**", inline=False)
    embed.add_field(name="👑 Premium Bot", value="✅ **Op voorraad**", inline=False)
    embed.set_footer(text="Gebruik /buy of open een ticket om te bestellen!")
    await interaction.response.send_message(embed=embed, ephemeral=False)


@tree.command(name="faq", description="Veelgestelde vragen over de bot-winkel")
async def faq(interaction: discord.Interaction):
    embed = discord.Embed(
        title="❓ Veelgestelde Vragen (FAQ)",
        color=discord.Color.orange()
    )
    embed.add_field(name="Hoe krijg ik mijn bot geleverd?", value="Na betaling configureren en hosten we de bot voor je of ontvang je de broncode.", inline=False)
    embed.add_field(name="Hoe kan ik betalen?", value="Via de Tikkie links met `/buy` of in overleg via een ticket.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=False)


@tree.command(name="review", description="Laat een review achter over de shop!")
@app_commands.describe(
    sterren="Kies hoeveel sterren (1 tot en met 5)", 
    recensie="Jouw ervaring of mening over de shop"
)
@app_commands.choices(sterren=[
    app_commands.Choice(name="⭐ 1 Ster", value=1),
    app_commands.Choice(name="⭐⭐ 2 Sterren", value=2),
    app_commands.Choice(name="⭐⭐⭐ 3 Sterren", value=3),
    app_commands.Choice(name="⭐⭐⭐⭐ 4 Sterren", value=4),
    app_commands.Choice(name="⭐⭐⭐⭐⭐ 5 Sterren", value=5)
])
async def review(interaction: discord.Interaction, sterren: int, recensie: str):
    sterren_weergave = "⭐" * sterren

    embed = discord.Embed(
        title="💬 Nieuwe Klantenreview!",
        description=f"**Klant:** {interaction.user.mention}\n"
                    f"**Beoordeling:** {sterren_weergave} ({sterren}/5)\n\n"
                    f"**Recensie:**\n> {recensie}",
        color=discord.Color.purple(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text=f"Gebruiker ID: {interaction.user.id}")
    
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Bedankt voor je review! Hij is succesvol geplaatst.", ephemeral=True)


# --- SLASH COMMANDO'S: STAFF & BEHEER ---

@tree.command(name="announce", description="Plaats een officiële aankondiging met optionele foto (Staff)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(
    titel="De titel van de aankondiging", 
    bericht="De inhoud van de aankondiging", 
    foto="Optioneel: upload een afbeelding of foto"
)
async def announce(interaction: discord.Interaction, titel: str, bericht: str, foto: discord.Attachment = None):
    embed = discord.Embed(
        title=f"📢 {titel}",
        description=bericht,
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    
    if foto:
        embed.set_image(url=foto.url)

    await interaction.channel.send(content="@everyone", embed=embed)
    await interaction.response.send_message("✅ Aankondiging succesvol verzonden!", ephemeral=True)


@tree.command(name="say", description="Laat de bot een tekstbericht sturen met optionele media (Staff)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(
    bericht="Wat wil je dat de bot zegt?", 
    media="Optioneel: upload een foto of bestand"
)
async def say(interaction: discord.Interaction, bericht: str, media: discord.Attachment = None):
    if media:
        await interaction.channel.send(content=f"{bericht}\n{media.url}")
    else:
        await interaction.channel.send(content=bericht)
        
    await interaction.response.send_message("✅ Bericht succesvol verzonden!", ephemeral=True)


@tree.command(name="claim", description="Claim een openstaand ticket (Staff)")
@app_commands.checks.has_permissions(manage_channels=True)
async def claim(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔒 Ticket Geclaimd",
        description=f"Dit ticket is overgenomen door stafflid {interaction.user.mention}. Die helpt je zo verder!",
        color=discord.Color.orange()
    )
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Je hebt dit ticket geclaimd.", ephemeral=True)


@tree.command(name="shopkick", description="Kick een gebruiker uit de server (Staff)")
@app_commands.checks.has_permissions(kick_members=True)
async def shopkick(interaction: discord.Interaction, member: discord.Member, reden: str = "Geen reden opgegeven"):
    await member.kick(reason=reden)
    await interaction.response.send_message(f"✅ {member.mention} is gekickt. Reden: {reden}", ephemeral=True)


@tree.command(name="shopban", description="Ban een gebruiker uit de server (Staff)")
@app_commands.checks.has_permissions(ban_members=True)
async def shopban(interaction: discord.Interaction, member: discord.Member, reden: str = "Geen reden opgegeven"):
    await member.ban(reason=reden)
    await interaction.response.send_message(f"✅ {member.mention} is gebanned. Reden: {reden}", ephemeral=True)


# --- SLASH COMMANDO'S: PARTNER PANEL ---

@tree.command(name="partnerpanel", description="Plaats het partner paneel in het kanaal. (Staff)")
async def partnerpanel(interaction: discord.Interaction):
    if interaction.user.id not in OWNER_IDS:
        user_role_ids = [role.id for role in interaction.user.roles]
        toegestane_rollen = [ROLE_PARTNER_BEHEER, ROLE_NIEUW_PARTNER]
        if not any(r_id in user_role_ids for r_id in toegestane_rollen):
            await interaction.response.send_message("❌ Je hebt geen toestemming om dit commando te gebruiken.", ephemeral=True)
            return

    embed = discord.Embed(
        title="🤝 Word Partner met Discord Bot Winkel!",
        description="Wil jij een samenwerking starten met onze server? Klik dan op de knop hieronder om het aanvraagproces te starten via je privéberichten (DM)!",
        color=discord.Color.blurple()
    )
    await interaction.channel.send(embed=embed, view=PartnerStartView())
    await interaction.response.send_message("✅ Partnerpanel succesvol verzonden!", ephemeral=True)


# Start de bot
bot.run(TOKEN)