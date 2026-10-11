import os
import random
import asyncio
import datetime
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# Laad de configuratie uit het .env bestand
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ Geen DISCORD_TOKEN gevonden in het .env bestand!")

# Configureer de benodigde intents voor de bot
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# CONFIGURATIE & ID'S
# ==========================================
UNVERIFIED_ROLE_ID = 1558771402637705316
VERIFIED_ROLE_ID = 1553800258675409042
TICKET_COMMAND_ROLE_ID = 1551313880494374962
VERIFICATION_LOG_CHANNEL_ID = 1558788150086606948
WELCOME_CHANNEL_ID = 1551311044733968627
COUNTING_CHANNEL_ID = 1554604994961997918
ANTIRAID_LOG_CHANNEL_ID = 1553860034318958632  # Anti-raid logkanaal

TICKET_ROLE_MAPPING = {
    "Support": 1551318416353132544,
    "Marketing": 1551683186629812305,
    "Management+": 1551314657241858088,
    "Giveaway Claim": 1551678461930639522
}

VERIFICATION_WORDS = ["VERIFIED", "SECURITY", "DISCORD", "ACCESS", "PROTECT", "WELCOME"]

LOG_CHANNEL_IDS = {
    "tickets": 1553859073567494334,
    "leden": 1553860034318958632,
    "berichten": 1553860126308569261,
    "call": 1553860165499883591,
    "role": 1553860220755910806,
    "kanaal": 1553860275675992064
}

# Geheugen voor het telsysteem en anti-spam tracking
COUNTING_DATA = {COUNTING_CHANNEL_ID: {'current': 0, 'last_user': None}}
SPAM_TRACKER = {}

async def get_log_channel(guild: discord.Guild, name: str) -> discord.TextChannel | None:
    channel_id = LOG_CHANNEL_IDS.get(name)
    if not channel_id:
        return None
    channel = guild.get_channel(channel_id)
    if not channel:
        try:
            channel = await guild.fetch_channel(channel_id)
        except Exception:
            return None
    return channel


# ==========================================
# MODERATIE & BAN VIEW (Voor Verificatie & Anti-Raid)
# ==========================================
class ModerationActionView(discord.ui.View):
    def __init__(self, target_member_id: int):
        super().__init__(timeout=None)
        self.target_member_id = target_member_id

    @discord.ui.button(label="Ban User", style=discord.ButtonStyle.danger, emoji="🔨", custom_id="mod_ban_btn_global")
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.ban_members:
            await interaction.followup.send("❌ Geen permissie om leden te bannen.", ephemeral=True)
            return
        guild = interaction.guild
        member = guild.get_member(self.target_member_id)
        try:
            if member:
                await guild.ban(member, reason=f"Gebanned via log door {interaction.user}")
            else:
                user = await bot.fetch_user(self.target_member_id)
                await guild.ban(user, reason=f"Gebanned via log door {interaction.user}")
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
            await interaction.followup.send(f"🔨 Gebruiker is gebanned door {interaction.user.mention}.", ephemeral=False)
        except Exception as e:
            await interaction.followup.send(f"❌ Fout bij bannen: {e}", ephemeral=True)

    @discord.ui.button(label="Kick User", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="mod_kick_btn_global")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.kick_members:
            await interaction.followup.send("❌ Geen permissie om leden te kicken.", ephemeral=True)
            return
        guild = interaction.guild
        member = guild.get_member(self.target_member_id)
        try:
            if member:
                await guild.kick(member, reason=f"Gekicked via log door {interaction.user}")
                for child in self.children:
                    child.disabled = True
                await interaction.message.edit(view=self)
                await interaction.followup.send(f"🛡️ Gebruiker is gekicked door {interaction.user.mention}.", ephemeral=False)
            else:
                await interaction.followup.send("⚠️ Gebruiker niet gevonden op de server.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Fout bij kicken: {e}", ephemeral=True)


# ==========================================
# VERIFICATIE SYSTEEM
# ==========================================
class VerificationModal(discord.ui.Modal):
    def __init__(self, target_word: str):
        super().__init__(title="Server Beveiliging Verificatie")
        self.target_word = target_word
        self.word_input = discord.ui.TextInput(
            label=f"Typ exact het woord: {target_word}",
            placeholder=target_word,
            required=True,
            max_length=20
        )
        self.add_item(self.word_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.word_input.value.strip().upper() == self.target_word:
            guild = interaction.guild
            member = interaction.user
            unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
            verified_role = guild.get_role(VERIFIED_ROLE_ID)
            
            if not unverified_role or not verified_role:
                await interaction.followup.send("⚠️ Configuratiefout: Rollen niet gevonden.", ephemeral=True)
                return

            try:
                if unverified_role in member.roles:
                    await member.remove_roles(unverified_role, reason="Verificatie voltooid")
                await member.add_roles(verified_role, reason="Verificatie voltooid")
                await interaction.followup.send("✅ Verificatie geslaagd! Je hebt nu toegang.", ephemeral=True)

                log_channel = guild.get_channel(VERIFICATION_LOG_CHANNEL_ID)
                if not log_channel:
                    try:
                        log_channel = await guild.fetch_channel(VERIFICATION_LOG_CHANNEL_ID)
                    except Exception:
                        log_channel = None

                if log_channel:
                    created_at = member.created_at
                    now = datetime.datetime.now(datetime.timezone.utc)
                    delta = now - created_at
                    age_str = f"{delta.days // 365} jaar, {(delta.days % 365) // 30} maanden"

                    embed = discord.Embed(
                        title="🛡️ Lid Geverifieerd",
                        description=f"Gebruiker {member.mention} heeft de verificatie doorlopen.",
                        color=discord.Color.green(),
                        timestamp=now
                    )
                    if member.display_avatar:
                        embed.set_thumbnail(url=member.display_avatar.url)
                    embed.add_field(name="👤 Naam", value=f"`{member.name}`", inline=True)
                    embed.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
                    embed.add_field(name="📅 Leeftijd", value=f"{created_at.strftime('%d-%m-%Y')} ({age_str})", inline=False)
                    
                    view = ModerationActionView(target_member_id=member.id)
                    await log_channel.send(embed=embed, view=view)
            except Exception as e:
                await interaction.followup.send(f"❌ Fout bij toekennen rollen: {e}", ephemeral=True)
        else:
            await interaction.followup.send("❌ Verificatie mislukt. Onjuist woord.", ephemeral=True)


class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verifiëren", style=discord.ButtonStyle.success, emoji="🔒", custom_id="verify_btn_antiraid")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerificationModal(target_word=random.choice(VERIFICATION_WORDS)))


# ==========================================
# TICKET SYSTEEM
# ==========================================
class TicketControlView(discord.ui.View):
    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener = opener
        self.claimed_by = None

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.primary, emoji="📌", custom_id="ticket_claim_btn_antiraid")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        channel = interaction.channel
        staff_member = interaction.user

        allowed_roles = list(TICKET_ROLE_MAPPING.values())
        is_staff = any(r.id in allowed_roles for r in staff_member.roles) or staff_member.guild_permissions.administrator
        if not is_staff:
            await interaction.followup.send("❌ Alleen medewerkers kunnen dit claimen.", ephemeral=True)
            return

        self.claimed_by = staff_member
        try:
            for role_id in allowed_roles:
                role = guild.get_role(role_id)
                if role:
                    await channel.set_permissions(role, send_messages=False)
            await channel.set_permissions(staff_member, send_messages=True, view_channel=True)

            button.disabled = True
            button.label = f"Geclaimd door {staff_member.display_name}"
            await interaction.message.edit(view=self)
            await interaction.followup.send(f"📌 Geclaimd door {staff_member.mention}.")
        except Exception as e:
            await interaction.followup.send(f"❌ Fout: {e}", ephemeral=True)

    @discord.ui.button(label="Sluit Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close_btn_antiraid")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        channel = interaction.channel
        closer = interaction.user

        await interaction.followup.send("⚠️ Transcript wordt gemaakt, kanaal sluit over 5 seconden...", ephemeral=False)

        transcript = f"<html><body><h2>Transcript: {channel.name}</h2><hr>"
        async for msg in channel.history(limit=None, oldest_first=True):
            transcript += f"<p><b>{msg.author}</b> ({msg.created_at.strftime('%d-%m-%Y %H:%M')}): {msg.content}</p>"
        transcript += "</body></html>"

        filename = f"transcript-{channel.name}.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(transcript)

        log_channel = await get_log_channel(guild, "tickets")
        if log_channel:
            embed = discord.Embed(title=f"🔒 Ticket Gearchiveerd — {channel.name}", color=discord.Color.red())
            embed.add_field(name="📂 Geopend door", value=self.opener.mention, inline=True)
            embed.add_field(name="🔒 Gesloten door", value=closer.mention, inline=True)
            file = discord.File(filename)
            await log_channel.send(embed=embed, file=file)

        if os.path.exists(filename):
            os.remove(filename)

        await asyncio.sleep(5)
        try:
            await channel.delete()
        except Exception:
            pass


class TicketCreateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        category_name = f"{ticket_type} Tickets"
        safe_name = ticket_type.lower().replace('+', '-plus').replace(' ', '-')
        
        existing = discord.utils.get(guild.text_channels, name=f"{safe_name}-{member.name.lower()}")
        if existing:
            await interaction.followup.send(f"❌ Je hebt al een open ticket: {existing.mention}", ephemeral=True)
            return

        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            try:
                category = await guild.create_category(category_name)
            except Exception:
                pass

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }

        staff_role = guild.get_role(TICKET_ROLE_MAPPING.get(ticket_type))
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        ticket_channel = await guild.create_text_channel(
            name=f"{safe_name}-{member.name}",
            category=category,
            overwrites=overwrites
        )

        embed = discord.Embed(
            title=f"🎫 {ticket_type} Ticket",
            description=f"Welkom {member.mention}! Stel hieronder je vraag.",
            color=discord.Color.blue()
        )
        await ticket_channel.send(content=staff_role.mention if staff_role else "", embed=embed, view=TicketControlView(opener=member))
        await interaction.followup.send(f"✅ Ticket aangemaakt: {ticket_channel.mention}", ephemeral=True)

    @discord.ui.button(label="Support", style=discord.ButtonStyle.primary, emoji="🛠️", custom_id="btn_support_antiraid")
    async def support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Support")

    @discord.ui.button(label="Marketing", style=discord.ButtonStyle.primary, emoji="📈", custom_id="btn_marketing_antiraid")
    async def marketing(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Marketing")

    @discord.ui.button(label="Management+", style=discord.ButtonStyle.primary, emoji="👑", custom_id="btn_management_antiraid")
    async def management(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Management+")

    @discord.ui.button(label="Giveaway Claim", style=discord.ButtonStyle.success, emoji="🎉", custom_id="btn_giveaway_antiraid")
    async def giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Giveaway Claim")


# ==========================================
# OPSTARTEN & COMMANDS
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Ingelogd als {bot.user}!")
    bot.add_view(VerificationView())
    bot.add_view(TicketCreateView())
    
    try:
        await bot.tree.sync()
        print("🔗 Slash-commando's gesynchroniseerd.")
    except Exception as e:
        print(f"❌ Fout bij sync: {e}")


# ==========================================
# TELSYSTEEM & ANTI-RAID / AUTO-MODERATIE
# ==========================================
@bot.tree.command(name="telkanalsetup", description="Plaats de uitleg voor het telsysteem in het officiële telkanaal.")
async def telkanalsetup(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Alleen beheerders kunnen dit instellen.", ephemeral=True)
        return

    if interaction.channel.id != COUNTING_CHANNEL_ID:
        await interaction.response.send_message(f"❌ Dit commando kan alleen worden gebruikt in het toegewezen telkanaal (<#{COUNTING_CHANNEL_ID}>).", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔢 Welkom bij het Telsysteem!",
        description="Laten we samen zo ver mogelijk komen! Hier zijn de regels:\n\n"
                    "• Typ om de beurt het volgende getal (1, 2, 3, 4...).<br>"
                    "• Je mag **niet** twee keer achter elkaar hetzelfde getal sturen of twee keer achter elkaar tellen.<br>"
                    "• Bij een goed getal krijg je een **✅**.<br>"
                    "• Bij een fout getal of dubbel getal wordt de teller direct **gereset naar 1**!<br>"
                    "• Let op: Als je echte tekst typt (chatten in plaats van getallen), krijg je een **mute van 5 minuten**!<br><br>"
                    "Veel succes!",
        color=discord.Color.from_rgb(241, 196, 15)
    )
    embed.set_footer(text="Prize Network • Telsysteem")
    
    await interaction.channel.send(embed=embed)
    COUNTING_DATA[COUNTING_CHANNEL_ID] = {'current': 0, 'last_user': None}
    await interaction.response.send_message("✅ Telsysteem succesvol ingesteld in dit kanaal!", ephemeral=True)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # 1. ANTI-RAID & AUTO-MODERATIE (Links, NSFW, Tag Spam)
    guild = message.guild
    author = message.author
    
    # Check voor tags/mentions spam (5+ tags binnen 5 seconden)
    now = datetime.datetime.now(datetime.timezone.utc)
    if len(message.mentions) >= 5:
        try:
            await message.delete()
            await author.timeout(datetime.timedelta(hours=24), reason="Anti-Raid: Mass mentions / Tag spam")
            
            log_chan = guild.get_channel(ANTIRAID_LOG_CHANNEL_ID)
            if log_chan:
                embed = discord.Embed(title="🚨 Anti-Raid Triggered (Tag Spam)", color=discord.Color.red(), timestamp=now)
                embed.add_field(name="Gebruiker", value=f"{author.mention} (`{author.id}`)", inline=False)
                embed.add_field(name="Bericht", value=message.content or "*Geen tekst*", inline=False)
                view = ModerationActionView(target_member_id=author.id)
                await log_chan.send(embed=embed, view=view)
        except Exception:
            pass
        return

    # Check voor Links of mogelijke NSFW-inhoud (bijv. bijlagen met gevoelige inhoud of link-detectie)
    has_link = "http://" in message.content or "https://www.discord.gg" in message.content or "discord.com/invite" in message.content or "https://" in message.content
    has_nsfw_attachment = any(att.is_spoiler() or "nsfw" in att.filename.lower() for att in message.attachments)

    if has_link or has_nsfw_attachment:
        # Als de gebruiker geen administrator of medewerker is, grijpen we in
        is_mod = author.guild_permissions.manage_messages or author.guild_permissions.administrator
        if not is_mod:
            try:
                await message.delete()
                await author.timeout(datetime.timedelta(hours=24), reason="Anti-Raid: Ongewenste link of NSFW inhoud gedetecteerd")
                
                log_chan = guild.get_channel(ANTIRAID_LOG_CHANNEL_ID)
                if log_chan:
                    embed = discord.Embed(title="🚨 Anti-Raid Triggered (Link / NSFW)", color=discord.Color.red(), timestamp=now)
                    embed.add_field(name="Gebruiker", value=f"{author.mention} (`{author.id}`)", inline=False)
                    embed.add_field(name="Verzonden inhoud", value=message.content or "*Bijlage / Media*", inline=False)
                    embed.add_field(name="Kanaal", value=message.channel.mention, inline=False)
                    view = ModerationActionView(target_member_id=author.id)
                    await log_chan.send(embed=embed, view=view)
            except Exception:
                pass
            return

    # 2. TELSYSTEEM LOGICA
    if message.channel.id == COUNTING_CHANNEL_ID:
        data = COUNTING_DATA.setdefault(COUNTING_CHANNEL_ID, {'current': 0, 'last_user': None})
        
        try:
            number = int(message.content.strip())
        except ValueError:
            data['current'] = 0
            data['last_user'] = None
            try:
                await message.add_reaction("❌")
                await message.channel.send(f"❌ {author.mention} maakte een fout (dat is geen geldig getal). Jullie waren bij **1**. Begin opnieuw vanaf **1**!")
                await author.timeout(datetime.timedelta(minutes=5), reason="Gechat in telkanaal")
            except Exception:
                pass
            await bot.process_commands(message)
            return

        expected_number = data['current'] + 1

        if author.id == data['last_user']:
            data['current'] = 0
            data['last_user'] = None
            try:
                await message.add_reaction("❌")
                await message.channel.send(f"❌ {author.mention} maakte een fout (je mag niet twee keer achter elkaar tellen). Jullie waren bij **1**. Begin opnieuw vanaf **1**!")
            except Exception:
                pass
            await bot.process_commands(message)
            return

        if number == expected_number:
            data['current'] = number
            data['last_user'] = author.id
            try:
                await message.add_reaction("✅")
            except Exception:
                pass
        else:
            data['current'] = 0
            data['last_user'] = None
            try:
                await message.add_reaction("❌")
                await message.channel.send(f"❌ {author.mention} maakte een fout (verkeerd getal). Jullie waren bij **1**. Begin opnieuw vanaf **1**!")
            except Exception:
                pass

    await bot.process_commands(message)


# Paneel Commandos
@bot.tree.command(name="verificatiepanelpost", description="Plaats het verificatiepaneel in dit kanaal.")
async def verificatiepanelpost(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Alleen beheerders kunnen dit commando gebruiken.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔒 Server Verificatie",
        description="Welkom op de server! Om volledige toegang te krijgen tot de kanalen, dien je jezelf te verifiëren door op onderstaande knop te klikken en de instructies te volgen.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Beveiligingssysteem • Klik op de knop om te starten.")
    
    await interaction.channel.send(embed=embed, view=VerificationView())
    await interaction.response.send_message("✅ Het verificatiepaneel is succesvol geplaatst in dit kanaal.", ephemeral=True)

@bot.tree.command(name="ticketpanelpost", description="Plaats het ticketpaneel.")
async def ticketpanelpost(interaction: discord.Interaction):
    if TICKET_COMMAND_ROLE_ID not in [r.id for r in interaction.user.roles] and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Geen rechten om dit paneel te plaatsen.", ephemeral=True)
        return
    embed = discord.Embed(title="🎫 Ticket Systeem", description="Kies hieronder een categorie om een ticket te openen.", color=discord.Color.purple())
    await interaction.channel.send(embed=embed, view=TicketCreateView())
    await interaction.response.send_message("✅ Ticketpaneel geplaatst.", ephemeral=True)


# ==========================================
# EVENT LISTENERS (Logging & Welkom)
# ==========================================
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    unverified = guild.get_role(UNVERIFIED_ROLE_ID)
    if unverified:
        try:
            await member.add_roles(unverified)
        except Exception:
            pass

    welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
    if not welcome_channel:
        try:
            welcome_channel = await guild.fetch_channel(WELCOME_CHANNEL_ID)
        except Exception:
            welcome_channel = None

    if welcome_channel:
        embed = discord.Embed(
            title="✨ Welkom bij Prize Network! ✨",
            description=f"Hallo {member.mention}, geweldig dat je er bent!\n\n"
                        f"• Vergeet niet om jezelf te **verifiëren** om toegang te krijgen tot de server.\n"
                        f"• Bekijk onze kanalen en doe gezellig mee.\n\n"
                        f"We wensen je heel veel plezier hier!",
            color=discord.Color.from_rgb(52, 152, 219),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Je bent lid nummer {guild.member_count} • Veel succes!", icon_url=guild.icon.url if guild.icon else None)
        
        await welcome_channel.send(embed=embed)

    channel = await get_log_channel(guild, "leden")
    if channel:
        await channel.send(embed=discord.Embed(title="📥 Lid Binnengekomen", description=f"{member.mention} is gejoined.", color=discord.Color.green()))

@bot.event
async def on_member_remove(member: discord.Member):
    channel = await get_log_channel(member.guild, "leden")
    if channel:
        await channel.send(embed=discord.Embed(title="📤 Lid Verlaten", description=f"{member.mention} heeft verlaten.", color=discord.Color.red()))

bot.run(TOKEN)
