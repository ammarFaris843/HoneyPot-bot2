import discord
import os
import json
import aiohttp
from datetime import datetime, timedelta, timezone

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

BOT_OWNERS = {322362428883206145}

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

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
                else:
                    text = await resp.text()
                    print(f"⚠️ Database error ({resp.status}): {text[:100]}")
                    return False
    except Exception as e:
        print(f"⚠️ Database connection unavailable: {str(e)[:100]}")
        return False

async def get_guild_config(guild_id):
    """Get configuration for a specific guild"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Accept': 'application/vnd.pgrst.object+json'
        }
        
        url = f"{SUPABASE_URL}/rest/v1/guild_configs?guild_id=eq.{guild_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list) and data:
                        return data[0]
                    elif isinstance(data, dict):
                        return data
                    else:
                        # Create default config
                        await save_guild_config(guild_id, None, None)
                        return await get_guild_config(guild_id)
                elif resp.status == 404:
                    # Table doesn't exist yet, create config
                    await save_guild_config(guild_id, None, None)
                    return await get_guild_config(guild_id)
                return None
    except Exception as e:
        # Silently fail for now
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
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as resp:
                return resp.status in [200, 201, 204]
    except Exception as e:
        # Silently fail
        return False

async def log_ban_to_db(guild_id, user_id, username, ban_reason, indicators):
    """Log a ban to the database"""
    if not SUPABASE_URL or not SUPABASE_KEY:
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
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as resp:
                return resp.status in [200, 201, 204]
    except Exception as e:
        # Silently fail
        return False

async def get_ban_history(guild_id):
    """Get ban history for a guild"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Accept': 'application/vnd.pgrst.object+json'
        }
        
        url = f"{SUPABASE_URL}/rest/v1/ban_history?guild_id=eq.{guild_id}&order=banned_at.desc&limit=10"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data if isinstance(data, list) else []
                return []
    except Exception as e:
        # Silently fail
        return []

def get_honeypot_channel(guild):
    return None  # Will be fetched when needed

def get_log_channel(guild):
    return None  # Will be fetched when needed

@client.event
async def on_ready():
    print(f'{client.user} is now online!')
    activity = discord.Activity(type=discord.ActivityType.watching, name="the honeypot 🪤")
    await client.change_presence(activity=activity)
    
    for guild in client.guilds:
        guild_config = await get_guild_config(guild.id)
        honeypot_id = guild_config.get("honeypot_channel_id") if guild_config else None
        log_id = guild_config.get("log_channel_id") if guild_config else None
        
        status = "✅" if honeypot_id and log_id else "⚠️"
        print(f"{status} {guild.name} (ID: {guild.id}) - Honeypot: {honeypot_id}, Log: {log_id}")

def analyze_username(username):
    indicators = []
    suspicious_patterns = [
        '⛧', '卐', '••', '||', '[]', '()', '⚡', '♛', '✪',
        'http', '.com', '.gg', 'discord.gg',
        '000', '111', '222', '333', '444', '555',
        'xxx', 'nsfw', 'click', 'free'
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
        ban_reason = guild_config.get("ban_reason", "Automatic ban: Suspected compromised account/bot") if guild_config else "Automatic ban: Suspected compromised account/bot"
        await member.ban(reason=ban_reason + f" | Indicators: {', '.join(indicators)}", delete_message_days=1)
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
        embed = discord.Embed(title="🪤 Honeypot Triggered", color=0xffa500, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User", value=f"{user.mention}\n`{user}`\nID: `{user.id}`", inline=False)
        truncated = message_content[:500] + "..." if len(message_content) > 500 else message_content
        embed.add_field(name="Message", value=f"```{truncated}```", inline=False)
        embed.add_field(name="Account Created", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Indicators", value="\n".join(indicators) if indicators else "None", inline=True)
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
        embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User", value=f"{user.mention}\n`{user}`", inline=False)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
        embed.add_field(name="Indicators", value=f"{len(indicators)}", inline=True)
        if indicators:
            embed.add_field(name="Details", value="• " + "\n• ".join(indicators), inline=False)
        if not success:
            embed.add_field(name="Note", value="Check bot permissions.", inline=False)
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
        print(f"Honeypot triggered by {message.author} (ID: {message.author.id})")
        print(f"Message: {message.content}")
        print(f"Indicators: {indicators}")
        await message.delete()
        await log_detection(message.guild, message.author, message.content, indicators)
        ban_success = await ban_user(member, indicators, message.guild)
        await log_ban_result(message.guild, message.author, ban_success, indicators)
        
        # Log ban to database
        if ban_success:
            guild_config = await get_guild_config(message.guild.id)
            ban_reason = guild_config.get("ban_reason") if guild_config else "Automatic ban: Suspected compromised account/bot"
            await log_ban_to_db(message.guild.id, message.author.id, str(message.author), ban_reason, indicators)
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
    honeypot_id = guild_config.get("honeypot_channel_id") if guild_config else None
    
    if honeypot_id and message.channel.id == honeypot_id:
        await handle_honeypot_trigger(message)
        return
    
    if message.content.startswith('!sethoneypot'):
        if not is_admin(message.author, message.guild):
            await message.channel.send("❌ You need administrator permissions.")
            return
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send("Usage: `!sethoneypot <channel_id>`")
            return
        try:
            channel_id = int(parts[1])
            channel = message.guild.get_channel(channel_id)
            if not channel:
                await message.channel.send("❌ Channel not found.")
                return
            guild_config = await get_guild_config(message.guild.id)
            log_id = guild_config.get("log_channel_id") if guild_config else None
            if await save_guild_config(message.guild.id, channel_id, log_id):
                await message.channel.send(f"✅ Honeypot channel set to {channel.mention}")
            else:
                await message.channel.send("❌ Failed to save configuration.")
        except ValueError:
            await message.channel.send("❌ Invalid channel ID.")
        return
    
    if message.content.startswith('!setlog'):
        if not is_admin(message.author, message.guild):
            await message.channel.send("❌ You need administrator permissions.")
            return
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send("Usage: `!setlog <channel_id>`")
            return
        try:
            channel_id = int(parts[1])
            channel = message.guild.get_channel(channel_id)
            if not channel:
                await message.channel.send("❌ Channel not found.")
                return
            guild_config = await get_guild_config(message.guild.id)
            honeypot_id = guild_config.get("honeypot_channel_id") if guild_config else None
            if await save_guild_config(message.guild.id, honeypot_id, channel_id):
                await message.channel.send(f"✅ Log channel set to {channel.mention}")
            else:
                await message.channel.send("❌ Failed to save configuration.")
        except ValueError:
            await message.channel.send("❌ Invalid channel ID.")
        return
    
    if message.content.startswith('!createhoneypot'):
        if not is_admin(message.author, message.guild):
            await message.channel.send("❌ You need administrator permissions.")
            return
        parts = message.content.split(maxsplit=1)
        name = parts[1] if len(parts) > 1 else "🪤-honeypot"
        try:
            channel = await message.guild.create_text_channel(
                name,
                reason="Honeypot channel created by bot",
                topic="🚨 This channel is monitored. Do not message here."
            )
            guild_config = await get_guild_config(message.guild.id)
            log_id = guild_config.get("log_channel_id") if guild_config else None
            if await save_guild_config(message.guild.id, channel.id, log_id):
                await message.channel.send(f"✅ Created honeypot channel: {channel.mention}\nChannel ID: `{channel.id}`")
            else:
                await message.channel.send("❌ Failed to save configuration.")
        except Exception as e:
            await message.channel.send(f"❌ Error creating channel: {e}")
        return
    
    if message.content.startswith('!createlog'):
        if not is_admin(message.author, message.guild):
            await message.channel.send("❌ You need administrator permissions.")
            return
        parts = message.content.split(maxsplit=1)
        name = parts[1] if len(parts) > 1 else "🔍-honeypot-logs"
        try:
            channel = await message.guild.create_text_channel(
                name,
                reason="Log channel created by bot"
            )
            await channel.set_permissions(message.guild.default_role, read_messages=False)
            guild_config = await get_guild_config(message.guild.id)
            honeypot_id = guild_config.get("honeypot_channel_id") if guild_config else None
            if await save_guild_config(message.guild.id, honeypot_id, channel.id):
                await message.channel.send(f"✅ Created log channel: {channel.mention}\nChannel ID: `{channel.id}`")
            else:
                await message.channel.send("❌ Failed to save configuration.")
        except Exception as e:
            await message.channel.send(f"❌ Error creating channel: {e}")
        return
    
    if message.content.startswith('!honeypotconfig'):
        if not is_admin(message.author, message.guild):
            await message.channel.send("❌ You need administrator permissions.")
            return
        guild_config = await get_guild_config(message.guild.id)
        honeypot_channel = None
        log_channel = None
        if guild_config:
            if guild_config.get("honeypot_channel_id"):
                honeypot_channel = message.guild.get_channel(guild_config["honeypot_channel_id"])
            if guild_config.get("log_channel_id"):
                log_channel = message.guild.get_channel(guild_config["log_channel_id"])
        
        embed = discord.Embed(title="🪤 Honeypot Configuration", color=0x7289da, timestamp=datetime.now(timezone.utc))
        embed.add_field(
            name="Honeypot Channel",
            value=f"{honeypot_channel.mention} (`{honeypot_channel.id}`)" if honeypot_channel else "Not set",
            inline=False
        )
        embed.add_field(
            name="Log Channel",
            value=f"{log_channel.mention} (`{log_channel.id}`)" if log_channel else "Not set",
            inline=False
        )
        embed.add_field(name="Ban Reason", value=guild_config.get("ban_reason", "Not set") if guild_config else "Not set", inline=False)
        embed.set_footer(text="Use !honeypothelp for commands")
        await message.channel.send(embed=embed)
        return
    
    if message.content.startswith('!honeypothelp'):
        embed = discord.Embed(title="🪤 Honeypot Bot Commands", color=0x00ff00)
        embed.add_field(name="!createhoneypot [name]", value="Create a new honeypot channel", inline=False)
        embed.add_field(name="!createlog [name]", value="Create a new log channel", inline=False)
        embed.add_field(name="!sethoneypot <channel_id>", value="Set existing channel as honeypot", inline=False)
        embed.add_field(name="!setlog <channel_id>", value="Set existing channel as log", inline=False)
        embed.add_field(name="!honeypotconfig", value="View current configuration", inline=False)
        embed.add_field(name="!honeypotstats", value="View bot statistics", inline=False)
        embed.add_field(name="!banhistory", value="View ban history for this server", inline=False)
        embed.set_footer(text="All commands require administrator permissions")
        await message.channel.send(embed=embed)
        return
    
    if message.content.startswith('!honeypotstats'):
        if not is_admin(message.author, message.guild):
            await message.channel.send("❌ You need administrator permissions.")
            return
        guild_config = await get_guild_config(message.guild.id)
        honeypot_channel = None
        log_channel = None
        if guild_config:
            if guild_config.get("honeypot_channel_id"):
                honeypot_channel = message.guild.get_channel(guild_config["honeypot_channel_id"])
            if guild_config.get("log_channel_id"):
                log_channel = message.guild.get_channel(guild_config["log_channel_id"])
        
        embed = discord.Embed(title="📊 Honeypot Statistics", color=0x7289da, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Server", value=message.guild.name, inline=True)
        embed.add_field(name="Honeypot Channel", value=honeypot_channel.mention if honeypot_channel else "Not set", inline=True)
        embed.add_field(name="Log Channel", value=log_channel.mention if log_channel else "Not set", inline=True)
        embed.add_field(name="Bot Latency", value=f"{round(client.latency * 1000)}ms", inline=True)
        embed.add_field(name="Members", value=message.guild.member_count, inline=True)
        status = "✅ Active" if honeypot_channel and log_channel else "⚠️ Setup needed"
        embed.add_field(name="Status", value=status, inline=True)
        embed.set_footer(text="Honeypot Protection System")
        await message.channel.send(embed=embed)
        return
    
    if message.content.startswith('!banhistory'):
        if not is_admin(message.author, message.guild):
            await message.channel.send("❌ You need administrator permissions.")
            return
        
        bans = await get_ban_history(message.guild.id)
        
        if not bans:
            await message.channel.send("📭 No bans recorded for this server yet.")
            return
        
        embed = discord.Embed(title="📋 Ban History", color=0xff0000, timestamp=datetime.now(timezone.utc))
        
        for ban in bans:
            ban_time = ban['banned_at'].replace('T', ' ').replace('Z', ' UTC') if 'T' in ban['banned_at'] else ban['banned_at']
            embed.add_field(
                name=f"User: {ban['banned_username']} (ID: {ban['banned_user_id']})",
                value=f"**Reason:** {ban['ban_reason']}\n**Indicators:** {ban['indicators']}\n**Banned:** {ban_time}",
                inline=False
            )
        
        embed.set_footer(text="Last 10 bans")
        await message.channel.send(embed=embed)
        return

from keep_alive import keep_alive

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
    keep_alive()
    token = os.getenv('DISCORD_BOT_TOKEN')
    if token:
        print("Starting honeypot bot with Supabase database...")
        client.run(token)
    else:
        print("ERROR: DISCORD_BOT_TOKEN not set!")
