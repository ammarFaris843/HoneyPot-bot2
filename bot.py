import discord
from discord import app_commands
import os
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

BOT_OWNERS = {322362428883206145}

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Render deployment URL for keep-alive pings
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')

# Caching
GUILD_CONFIG_CACHE = {}
BAN_HISTORY_CACHE = {}
CACHE_TTL = 600  # 10 minutes
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)
session = None  # Global session for connection pooling


async def init_db():
    """Initialize database tables via Supabase REST API"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ Supabase credentials not set. Database features disabled.")
        return False

    try:
        async with aiohttp.ClientSession() as session:
            # Test connection
            headers = {
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
                'Accept': 'application/vnd.pgrst.object+json'
            }

            url = f"{SUPABASE_URL}/rest/v1/guild_configs?limit=1"
            async with session.get(url, headers=headers) as resp:
                if resp.status in [200, 404]:
                    print("✅ Database initialized successfully")
                    return True
                elif resp.status == 401:
                    print(
                        "⚠️ Database error: Invalid Supabase credentials (401 Unauthorized)"
                    )
                    return False
                else:
                    text = await resp.text()
                    print(f"⚠️ Database error ({resp.status}): {text[:150]}")
                    return False
    except Exception as e:
        error_type = type(e).__name__
        if 'Connection' in error_type:
            print(f"⚠️ Cannot reach Supabase - check SUPABASE_URL is correct")
        elif 'Timeout' in error_type:
            print(f"⚠️ Supabase connection timeout - server may be slow")
        else:
            print(f"⚠️ Database connection error: {error_type}")
        return False


async def get_guild_config(guild_id):
    """Get configuration for a specific guild (with caching)"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    # Check cache first
    if guild_id in GUILD_CONFIG_CACHE:
        cached_data, timestamp = GUILD_CONFIG_CACHE[guild_id]
        if datetime.now(timezone.utc).timestamp() - timestamp < CACHE_TTL:
            return cached_data

    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}'
        }

        url = f"{SUPABASE_URL}/rest/v1/guild_configs?guild_id=eq.{guild_id}"
        async with session.get(url, headers=headers, timeout=HTTP_TIMEOUT) as resp:
            if resp.status == 200:
                data = await resp.json()
                result = data[0] if isinstance(data, list) and data else (
                    data if isinstance(data, dict) else None)
                if result:
                    # Cache it
                    GUILD_CONFIG_CACHE[guild_id] = (
                        result, datetime.now(timezone.utc).timestamp())
                    return result
                else:
                    await save_guild_config(guild_id, None, None)
                    return await get_guild_config(guild_id)
            elif resp.status == 404:
                await save_guild_config(guild_id, None, None)
                return await get_guild_config(guild_id)
                return None
    except Exception as e:
        return None


async def save_guild_config(guild_id, honeypot_channel_id, log_channel_id):
    """Save configuration for a specific guild"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates'
        }

        data = {
            'guild_id': guild_id,
            'honeypot_channel_id': honeypot_channel_id,
            'log_channel_id': log_channel_id,
            'ban_reason': 'Automatic ban: Suspected compromised account/bot'
        }

        url = f"{SUPABASE_URL}/rest/v1/guild_configs"
        async with session.post(url, json=data, headers=headers, timeout=HTTP_TIMEOUT) as resp:
            success = resp.status in [200, 201, 204]
            if success:
                GUILD_CONFIG_CACHE.pop(guild_id, None)
            return success
    except Exception as e:
        return False


async def log_ban_to_db(guild_id, user_id, username, ban_reason, indicators):
    """Log a ban to the database"""
    if not SUPABASE_URL or not SUPABASE_KEY or not session:
        return False

    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'
        }

        indicators_str = ', '.join(indicators) if indicators else ''
        data = {
            'guild_id': guild_id,
            'banned_user_id': user_id,
            'banned_username': username,
            'ban_reason': ban_reason,
            'indicators': indicators_str
        }

        url = f"{SUPABASE_URL}/rest/v1/ban_history"
        async with session.post(url, json=data, headers=headers, timeout=HTTP_TIMEOUT) as resp:
            if resp.status in [200, 201, 204]:
                BAN_HISTORY_CACHE.pop(guild_id, None)
            return resp.status in [200, 201, 204]
    except Exception:
        return False


async def get_ban_history(guild_id):
    """Get ban history for a guild (with caching)"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    
    # Check cache first
    if guild_id in BAN_HISTORY_CACHE:
        cached_data, timestamp = BAN_HISTORY_CACHE[guild_id]
        if datetime.now(timezone.utc).timestamp() - timestamp < CACHE_TTL:
            return cached_data

    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}'
        }

        url = f"{SUPABASE_URL}/rest/v1/ban_history?guild_id=eq.{guild_id}&order=banned_at.desc&limit=10"
        async with session.get(url, headers=headers, timeout=HTTP_TIMEOUT) as resp:
            if resp.status == 200:
                data = await resp.json()
                result = data if isinstance(data, list) else []
                BAN_HISTORY_CACHE[guild_id] = (result, datetime.now(timezone.utc).timestamp())
                return result
            return []
    except Exception:
        return []


def get_honeypot_channel(guild):
    return None  # Will be fetched when needed


def get_log_channel(guild):
    return None  # Will be fetched when needed


async def keep_alive_ping():
    """Send periodic HTTPS requests to keep bot alive on Render"""
    await client.wait_until_ready()
    if not RENDER_EXTERNAL_URL:
        print("⚠️ RENDER_EXTERNAL_URL not set, skipping keep-alive pings")
        return
    
    while not client.is_closed():
        try:
            if session:
                # Send HTTPS request every 20 minutes to prevent Render shutdown
                async with session.get(RENDER_EXTERNAL_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status in [200, 404]:
                        print(f"🔄 Keep-alive ping sent to {RENDER_EXTERNAL_URL}")
        except Exception as e:
            print(f"⚠️ Keep-alive ping failed: {type(e).__name__}")
        
        # Wait 20 minutes before next ping
        await asyncio.sleep(1200)


@client.event
async def on_ready():
    global session
    if not session:
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        session = aiohttp.ClientSession(connector=connector, timeout=HTTP_TIMEOUT)

    await init_db()

    print(f'{client.user} is now online!')
    activity = discord.Activity(type=discord.ActivityType.watching,
                                name="the honeypot 🪤")
    await client.change_presence(activity=activity)

    # Start keep-alive background task (only once)
    if not any(task.get_name() == 'keep_alive_ping' for task in asyncio.all_tasks()):
        client.loop.create_task(keep_alive_ping(), name='keep_alive_ping')
        print("✅ Keep-alive ping started (sends HTTPS request every 20 minutes)")

    # Sync slash commands globally (fast & efficient)
    try:
        synced = await tree.sync()
        print(f"✅ Synced {len(synced)} command(s) globally")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

    for guild in client.guilds:
        guild_config = await get_guild_config(guild.id)
        honeypot_id = guild_config.get(
            "honeypot_channel_id") if guild_config else None
        log_id = guild_config.get("log_channel_id") if guild_config else None

        status = "✅" if honeypot_id and log_id else "⚠️"
        print(
            f"{status} {guild.name} (ID: {guild.id}) - Honeypot: {honeypot_id}, Log: {log_id}"
        )


def analyze_username(username):
    indicators = []
    suspicious_patterns = [
        '⛧', '卐', '••', '||', '[]', '()', '⚡', '♛', '✪', 'http', '.com', '.gg',
        'discord.gg', '000', '111', '222', '333', '444', '555', 'xxx', 'nsfw',
        'click', 'free'
    ]
    username_lower = username.lower()
    for pattern in suspicious_patterns:
        if pattern in username_lower:
            indicators.append(f"Suspicious username: '{pattern}'")
            break
    if len(username) > 25:
        indicators.append("Very long username")
    return indicators


def analyze_roles(member):
    indicators = []
    if len(member.roles) <= 1:
        indicators.append("No custom roles")
    return indicators


async def detect_suspicious_indicators(user, member):
    indicators = []
    now = datetime.now(timezone.utc)
    account_age = now - user.created_at
    if account_age < timedelta(days=1):
        indicators.append("Account <1 day old")
    elif account_age < timedelta(days=7):
        indicators.append("Account <7 days old")
    if member.joined_at:
        join_age = now - member.joined_at
        if join_age < timedelta(hours=1):
            indicators.append("Joined <1 hour ago")
        elif join_age < timedelta(hours=24):
            indicators.append("Joined <24 hours ago")
    if user.avatar is None:
        indicators.append("Default avatar")
    indicators.extend(analyze_username(user.name))
    indicators.extend(analyze_roles(member))
    return indicators


async def ban_user(member, indicators, guild):
    try:
        guild_config = await get_guild_config(guild.id)
        ban_reason = guild_config.get(
            "ban_reason", "Automatic ban: Suspected compromised account/bot"
        ) if guild_config else "Automatic ban: Suspected compromised account/bot"
        await member.ban(reason=ban_reason +
                         f" | Indicators: {', '.join(indicators)}",
                         delete_message_days=1)
        print(f"Successfully banned {member} (ID: {member.id})")
        return True
    except discord.Forbidden:
        print(f"Missing permissions to ban {member}")
        return False
    except Exception as e:
        print(f"Error banning {member}: {e}")
        return False


async def log_detection(guild, user, message_content, indicators):
    log_config = await get_guild_config(guild.id)
    if not log_config or not log_config.get("log_channel_id"):
        return

    log_channel = guild.get_channel(log_config["log_channel_id"])
    if not log_channel:
        return

    try:
        embed = discord.Embed(title="Gooning to Kotuh 💔",
                              color=0xffa500,
                              timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User",
                        value=f"{user.mention}\n`{user}`\nID: `{user.id}`",
                        inline=False)
        truncated = message_content[:500] + "..." if len(
            message_content) > 500 else message_content
        embed.add_field(name="Message",
                        value=f"```{truncated}```",
                        inline=False)
        embed.add_field(name="Account Created",
                        value=f"<t:{int(user.created_at.timestamp())}:R>",
                        inline=True)
        embed.add_field(name="Indicators",
                        value="\n".join(indicators) if indicators else "None",
                        inline=True)
        if user.avatar:
            embed.set_thumbnail(url=user.display_avatar.url)
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging detection: {e}")


async def log_ban_result(guild, user, success, indicators):
    log_config = await get_guild_config(guild.id)
    if not log_config or not log_config.get("log_channel_id"):
        return

    log_channel = guild.get_channel(log_config["log_channel_id"])
    if not log_channel:
        return

    try:
        color = 0x00ff00 if success else 0xff0000
        title = "✅ User Banned" if success else "❌ Ban Failed"
        embed = discord.Embed(title=title,
                              color=color,
                              timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User",
                        value=f"{user.mention}\n`{user}`",
                        inline=False)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
        embed.add_field(name="Indicators",
                        value=f"{len(indicators)}",
                        inline=True)
        if indicators:
            embed.add_field(name="Details",
                            value="• " + "\n• ".join(indicators),
                            inline=False)
        if not success:
            embed.add_field(name="Note",
                            value="Check bot permissions.",
                            inline=False)
        embed.set_footer(text="Honeypot Protection")
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging ban result: {e}")


async def handle_honeypot_trigger(message):
    try:
        member = message.guild.get_member(message.author.id)
        if not member:
            return
        indicators = await detect_suspicious_indicators(message.author, member)
        print(
            f"Honeypot triggered by {message.author} (ID: {message.author.id})"
        )
        print(f"Message: {message.content}")
        print(f"Indicators: {indicators}")

        # Log detection first (before deletion)
        await log_detection(message.guild, message.author, message.content,
                            indicators)

        # Ban the user
        ban_success = await ban_user(member, indicators, message.guild)
        await log_ban_result(message.guild, message.author, ban_success,
                             indicators)

        # Log ban to database
        if ban_success:
            guild_config = await get_guild_config(message.guild.id)
            ban_reason = guild_config.get(
                "ban_reason"
            ) if guild_config else "Automatic ban: Suspected compromised account/bot"
            await log_ban_to_db(message.guild.id, message.author.id,
                                str(message.author), ban_reason, indicators)

        # Delete the message last (after all logging and banning)
        try:
            await message.delete()
        except discord.NotFound:
            pass  # Message already deleted, that's fine
    except Exception as e:
        print(f"Error processing honeypot: {e}")


def is_admin(member, guild):
    if member.id in BOT_OWNERS:
        return True
    if member.id == guild.owner_id:
        return True
    return any(role.permissions.administrator for role in member.roles)


@client.event
async def on_message(message):
    if message.author.bot:
        return

    guild_config = await get_guild_config(message.guild.id)
    honeypot_id = guild_config.get(
        "honeypot_channel_id") if guild_config else None

    if honeypot_id and message.channel.id == honeypot_id:
        await handle_honeypot_trigger(message)


# Slash Commands
@tree.command(name="sethoneypot",
              description="Set existing channel as honeypot")
@app_commands.describe(channel_id="The channel ID to set as honeypot")
async def sethoneypot(interaction: discord.Interaction, channel_id: str):
    if not is_admin(interaction.user, interaction.guild):
        await interaction.response.send_message(
            "❌ You need administrator permissions.", ephemeral=True)
        return
    try:
        ch_id = int(channel_id)
        channel = interaction.guild.get_channel(ch_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found.",
                                                    ephemeral=True)
            return
        guild_config = await get_guild_config(interaction.guild.id)
        log_id = guild_config.get("log_channel_id") if guild_config else None
        if await save_guild_config(interaction.guild.id, ch_id, log_id):
            await interaction.response.send_message(
                f"✅ Honeypot channel set to {channel.mention}")
            GUILD_CONFIG_CACHE.pop(interaction.guild.id, None)
        else:
            await interaction.response.send_message(
                "❌ Failed to save configuration.", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ Invalid channel ID.",
                                                ephemeral=True)


@tree.command(name="setlog", description="Set existing channel as log")
@app_commands.describe(channel_id="The channel ID to set as log")
async def setlog(interaction: discord.Interaction, channel_id: str):
    if not is_admin(interaction.user, interaction.guild):
        await interaction.response.send_message(
            "❌ You need administrator permissions.", ephemeral=True)
        return
    try:
        ch_id = int(channel_id)
        channel = interaction.guild.get_channel(ch_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found.",
                                                    ephemeral=True)
            return
        guild_config = await get_guild_config(interaction.guild.id)
        honeypot_id = guild_config.get(
            "honeypot_channel_id") if guild_config else None
        if await save_guild_config(interaction.guild.id, honeypot_id, ch_id):
            await interaction.response.send_message(
                f"✅ Log channel set to {channel.mention}")
            GUILD_CONFIG_CACHE.pop(interaction.guild.id, None)
        else:
            await interaction.response.send_message(
                "❌ Failed to save configuration.", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ Invalid channel ID.",
                                                ephemeral=True)


@tree.command(name="createhoneypot",
              description="Create a new honeypot channel")
@app_commands.describe(name="Name for the honeypot channel")
async def createhoneypot(interaction: discord.Interaction,
                         name: str = "🪤-honeypot"):
    if not is_admin(interaction.user, interaction.guild):
        await interaction.response.send_message(
            "❌ You need administrator permissions.", ephemeral=True)
        return
    try:
        await interaction.response.defer()
        channel = await interaction.guild.create_text_channel(
            name,
            reason="Honeypot channel created by bot",
            topic="🚨 This channel is monitored. Do not message here.")
        guild_config = await get_guild_config(interaction.guild.id)
        log_id = guild_config.get("log_channel_id") if guild_config else None
        if await save_guild_config(interaction.guild.id, channel.id, log_id):
            await interaction.followup.send(
                f"✅ Created honeypot channel: {channel.mention}\nChannel ID: `{channel.id}`"
            )
            GUILD_CONFIG_CACHE.pop(interaction.guild.id, None)
        else:
            await interaction.followup.send("❌ Failed to save configuration.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error creating channel: {e}")


@tree.command(name="createlog", description="Create a new log channel")
@app_commands.describe(name="Name for the log channel")
async def createlog(interaction: discord.Interaction,
                    name: str = "🔍-honeypot-logs"):
    if not is_admin(interaction.user, interaction.guild):
        await interaction.response.send_message(
            "❌ You need administrator permissions.", ephemeral=True)
        return
    try:
        await interaction.response.defer()
        channel = await interaction.guild.create_text_channel(
            name, reason="Log channel created by bot")
        await channel.set_permissions(interaction.guild.default_role,
                                      read_messages=False)
        guild_config = await get_guild_config(interaction.guild.id)
        honeypot_id = guild_config.get(
            "honeypot_channel_id") if guild_config else None
        if await save_guild_config(interaction.guild.id, honeypot_id,
                                   channel.id):
            await interaction.followup.send(
                f"✅ Created log channel: {channel.mention}\nChannel ID: `{channel.id}`"
            )
            GUILD_CONFIG_CACHE.pop(interaction.guild.id, None)
        else:
            await interaction.followup.send("❌ Failed to save configuration.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error creating channel: {e}")


@tree.command(name="honeypotconfig",
              description="View current honeypot configuration")
async def honeypotconfig(interaction: discord.Interaction):
    if not is_admin(interaction.user, interaction.guild):
        await interaction.response.send_message(
            "❌ You need administrator permissions.", ephemeral=True)
        return
    guild_config = await get_guild_config(interaction.guild.id)
    honeypot_channel = None
    log_channel = None
    if guild_config:
        if guild_config.get("honeypot_channel_id"):
            honeypot_channel = interaction.guild.get_channel(
                guild_config["honeypot_channel_id"])
        if guild_config.get("log_channel_id"):
            log_channel = interaction.guild.get_channel(
                guild_config["log_channel_id"])
    embed = discord.Embed(title="🪤 Honeypot Configuration",
                          color=0x7289da,
                          timestamp=datetime.now(timezone.utc))
    embed.add_field(
        name="Honeypot Channel",
        value=f"{honeypot_channel.mention} (`{honeypot_channel.id}`)"
        if honeypot_channel else "Not set",
        inline=False)
    embed.add_field(name="Log Channel",
                    value=f"{log_channel.mention} (`{log_channel.id}`)"
                    if log_channel else "Not set",
                    inline=False)
    embed.add_field(name="Ban Reason",
                    value=guild_config.get("ban_reason", "Not set")
                    if guild_config else "Not set",
                    inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="honeypotstats", description="View honeypot statistics")
async def honeypotstats(interaction: discord.Interaction):
    if not is_admin(interaction.user, interaction.guild):
        await interaction.response.send_message(
            "❌ You need administrator permissions.", ephemeral=True)
        return
    guild_config = await get_guild_config(interaction.guild.id)
    honeypot_channel = None
    log_channel = None
    if guild_config:
        if guild_config.get("honeypot_channel_id"):
            honeypot_channel = interaction.guild.get_channel(
                guild_config["honeypot_channel_id"])
        if guild_config.get("log_channel_id"):
            log_channel = interaction.guild.get_channel(
                guild_config["log_channel_id"])
    embed = discord.Embed(title="📊 Honeypot Statistics",
                          color=0x7289da,
                          timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Server", value=interaction.guild.name, inline=True)
    embed.add_field(
        name="Honeypot Channel",
        value=honeypot_channel.mention if honeypot_channel else "Not set",
        inline=True)
    embed.add_field(name="Log Channel",
                    value=log_channel.mention if log_channel else "Not set",
                    inline=True)
    embed.add_field(name="Bot Latency",
                    value=f"{round(client.latency * 1000)}ms",
                    inline=True)
    embed.add_field(name="Members",
                    value=interaction.guild.member_count,
                    inline=True)
    status = "✅ Active" if honeypot_channel and log_channel else "⚠️ Setup needed"
    embed.add_field(name="Status", value=status, inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="banhistory",
              description="View ban history for this server")
async def banhistory(interaction: discord.Interaction):
    if not is_admin(interaction.user, interaction.guild):
        await interaction.response.send_message(
            "❌ You need administrator permissions.", ephemeral=True)
        return
    if not SUPABASE_URL or not SUPABASE_KEY:
        await interaction.response.send_message("❌ Database not configured.",
                                                ephemeral=True)
        return
    await interaction.response.defer()
    bans = await get_ban_history(interaction.guild.id)
    if not bans:
        await interaction.followup.send(
            "📭 No bans recorded for this server yet.")
        return
    embed = discord.Embed(title="📋 Ban History",
                          color=0xff0000,
                          timestamp=datetime.now(timezone.utc))
    try:
        for ban in bans:
            ban_time = ban.get('banned_at', 'Unknown').replace(
                'T', ' '
            ).replace(
                'Z', ' UTC'
            ) if 'banned_at' in ban and 'T' in ban['banned_at'] else ban.get(
                'banned_at', 'Unknown')
            username = ban.get('banned_username', 'Unknown User')
            user_id = ban.get('banned_user_id', 'Unknown')
            reason = ban.get('ban_reason', 'No reason')
            indicators = ban.get('indicators', 'None detected')
            embed.add_field(
                name=f"User: {username} (ID: {user_id})",
                value=
                f"**Reason:** {reason}\n**Indicators:** {indicators}\n**Banned:** {ban_time}",
                inline=False)
        embed.set_footer(text=f"Last {len(bans)} ban(s)")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Error displaying ban history")
        print(f"Error in banhistory: {e}")


from keep_alive import keep_alive
import threading

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
    
    # Run Flask server in a background thread
    flask_thread = threading.Thread(target=keep_alive, daemon=True)
    flask_thread.start()
    
    token = os.getenv('DISCORD_BOT_TOKEN')
    if token:
        print("Starting honeypot bot with Supabase database...")
        client.run(token)
    else:
        print("ERROR: DISCORD_BOT_TOKEN not set!")
