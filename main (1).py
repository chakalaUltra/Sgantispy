
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Select, Button
import json
import os
from datetime import datetime, timezone, timedelta

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')  # Get token from environment variables
WARNINGS_FILE = 'warnings.json'
CONFIG_FILE = 'config.json'

# --- BOT INITIALIZATION ---
intents = discord.Intents.default()
intents.members = True # Required for member-related events and fetching members
intents.message_content = True # Required for prefix commands (though less so for this modified version)

bot = commands.Bot(command_prefix='$', intents=intents) # Prefix is still needed for other prefix commands

bot.config = {} # Initialize bot.config
bot.warnings = {} # Initialize bot.warnings

# --- BOT CONFIGURATION AND DATA HANDLING ---
def load_config():
    """Loads configuration from the JSON file into bot.config."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            bot.config = json.load(f)
            # Ensure new keys exist after loading old config
            if "guild_configs" not in bot.config:
                bot.config["guild_configs"] = {}
            for guild_id_str in bot.config["guild_configs"]:
                guild_config = bot.config["guild_configs"][guild_id_str]
                if "command_permissions" not in guild_config:
                    guild_config["command_permissions"] = {}
                if "log_settings" not in guild_config: # Ensure log_settings exists
                    guild_config["log_settings"] = {}
    except FileNotFoundError:
        bot.config = {
            "custom_ban_message": None,
            "guild_configs": {}
        }
        save_config()
    except json.JSONDecodeError:
        print(f"Error decoding '{CONFIG_FILE}'. Starting with default config.")
        bot.config = {
            "custom_ban_message": None,
            "guild_configs": {}
        }
    except Exception as e:
        print(f"An unexpected error occurred while loading config: {e}")
        bot.config = {
            "custom_ban_message": None,
            "guild_configs": {}
        }

def save_config():
    """Saves current bot.config to the JSON file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(bot.config, f, indent=4)
    except Exception as e:
        print(f"An error occurred while saving config: {e}")

def load_warnings():
    """Loads warnings from the JSON file into bot.warnings."""
    try:
        with open(WARNINGS_FILE, 'r') as f:
            bot.warnings = json.load(f)
    except FileNotFoundError:
        bot.warnings = {}
        save_warnings()
    except json.JSONDecodeError:
        print(f"Error decoding '{WARNINGS_FILE}'. Starting with empty warnings.")
        bot.warnings = {}
    except Exception as e:
        print(f"An unexpected error occurred while loading warnings: {e}")

def save_warnings():
    """Saves current bot.warnings to the JSON file."""
    try:
        with open(WARNINGS_FILE, 'w') as f:
            json.dump(bot.warnings, f, indent=4)
    except Exception as e:
        print(f"An error occurred while saving warnings: {e}")

# --- LOGGING UTILITY FUNCTION ---
async def send_log_embed(guild: discord.Guild, log_type: str, embed: discord.Embed):
    guild_config = bot.config.get("guild_configs", {}).get(str(guild.id), {})
    log_channel_id = guild_config.get("log_channel_id")
    log_settings = guild_config.get("log_settings", {})

    if log_channel_id and log_settings.get(log_type, True): # Default to True if setting not found
        log_channel = guild.get_channel(log_channel_id)
        if log_channel and isinstance(log_channel, discord.TextChannel):
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                print(f"Warning: Bot does not have permission to send messages to log channel {log_channel.id} in {guild.name}.")
            except Exception as e:
                print(f"Error sending log embed to {log_channel.name} in {guild.name}: {e}")
        else:
            print(f"Warning: Log channel {log_channel_id} not found or not a text channel in {guild.name}.")

# --- PERMISSION UTILITY FUNCTIONS ---
def has_permission(ctx_or_interaction):
    """Checks if the user has Discord's administrator permission."""
    if isinstance(ctx_or_interaction, discord.ext.commands.Context):
        member = ctx_or_interaction.author
    elif isinstance(ctx_or_interaction, discord.Interaction):
        member = ctx_or_interaction.user
    else:
        return False
    if not isinstance(member, discord.Member):
        return False
    return member.guild_permissions.administrator

async def check_command_permission(ctx_or_interaction, command_name: str) -> bool:
    """
    Checks if a user has permission to use a command, either by being a Discord admin
    or by having a role explicitly allowed via /perm-add.
    """
    if isinstance(ctx_or_interaction, discord.ext.commands.Context):
        member = ctx_or_interaction.author
        guild = ctx_or_interaction.guild
    elif isinstance(ctx_or_interaction, discord.Interaction):
        member = ctx_or_interaction.user
        guild = ctx_or_interaction.guild
    else:
        return False

    if not isinstance(member, discord.Member):
        return False

    # 1. Always allow if the user is a Discord administrator
    if member.guild_permissions.administrator:
        return True

    # 2. Check custom role permissions from config
    guild_config = bot.config.get("guild_configs", {}).get(str(guild.id), {})
    command_permissions = guild_config.get("command_permissions", {})

    allowed_role_ids_for_command = command_permissions.get(command_name, [])

    if not allowed_role_ids_for_command:
        # If no specific roles are set for this command, it's not custom-permissible for non-admins
        return False

    # Check if the member has any of the allowed roles
    for role in member.roles:
        if role.id in allowed_role_ids_for_command:
            return True
            
    return False

# --- TIME UTILITY FUNCTIONS ---
def human_timedelta(dt: datetime) -> str:
    """Converts a datetime object to a human-readable relative time string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 0: return "in the future"
    if seconds < 10: return "a few seconds ago"
    if seconds < 60: return f"{int(seconds)} second{'s' if seconds > 1 or seconds == 0 else ''} ago"
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} minute{'s' if minutes > 1 or minutes == 0 else ''} ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours > 1 or hours == 0 else ''} ago"
    if seconds < 2592000: # 30 days
        days = diff.days
        return f"{days} day{'s' if days > 1 or days == 0 else ''} ago"
    return dt.strftime("%Y-%m-%d %H:%M UTC")

def parse_duration(duration_str: str) -> timedelta | None:
    """Parses a duration string (e.g., '5m', '2h', '1d', '4w') into a timedelta object."""
    if not duration_str:
        return None

    duration_str = duration_str.lower()
    amount = 0
    unit = ''

    for char in duration_str:
        if char.isdigit():
            amount = amount * 10 + int(char)
        else:
            unit += char

    if amount == 0 and unit == '':
        return None

    if unit == 's':
        return timedelta(seconds=amount)
    elif unit == 'm':
        return timedelta(minutes=amount)
    elif unit == 'h':
        return timedelta(hours=amount)
    elif unit == 'd':
        return timedelta(days=amount)
    elif unit == 'w':
        return timedelta(weeks=amount)
    else:
        return None

# --- ON_READY EVENT ---
@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user} (ID: {bot.user.id})')
    load_warnings()
    load_config() # Load config data
    await bot.change_presence(
        status=discord.Status.idle,
        activity=discord.Activity(type=discord.ActivityType.watching, name="my coding progress 🔥") # Customize this text!
    )
    try:
        synced = await bot.tree.sync()
        print(f'Slash commands synced: {len(synced)} command(s)')
    except Exception as e:
        print(f'Error during bot setup (syncing slash commands): {e}')



# --- CONFIGURATION COMMANDS ---




@bot.tree.command(name="set-log-channel", description="Sets the channel for moderation logs.")
@app_commands.describe(channel="The channel to set as the log channel")
async def set_log_channel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    guild_id_str = str(interaction.guild.id)
    if guild_id_str not in bot.config["guild_configs"]:
        bot.config["guild_configs"][guild_id_str] = {
            "log_channel_id": None,
            "log_settings": {},
            "command_permissions": {}
        }
    bot.config["guild_configs"][guild_id_str]["log_channel_id"] = channel.id
    save_config()
    await interaction.response.send_message(f"Moderation log channel set to {channel.mention}.", ephemeral=True)

    log_embed = discord.Embed(
        title="Log Channel Set",
        description=f"Log channel has been set to {channel.mention} by {interaction.user.mention}.",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    log_embed.set_footer(text=f"Server: {interaction.guild.name}")
    await send_log_embed(interaction.guild, "config_change", log_embed)


@bot.tree.command(name="remove-log-channel", description="Removes the set moderation log channel.")
async def remove_log_channel_slash(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    guild_id_str = str(interaction.guild.id)
    if guild_id_str in bot.config["guild_configs"]:
        if bot.config["guild_configs"][guild_id_str].get("log_channel_id") is not None:
            log_channel_id = bot.config["guild_configs"][guild_id_str]["log_channel_id"]
            bot.config["guild_configs"][guild_id_str]["log_channel_id"] = None
            save_config()
            await interaction.response.send_message("Moderation log channel has been removed.", ephemeral=True)

            log_embed = discord.Embed(
                title="Log Channel Removed",
                description=f"Log channel (ID: {log_channel_id}) has been removed by {interaction.user.mention}.",
                color=discord.Color.dark_red(),
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.set_footer(text=f"Server: {interaction.guild.name}")
            removed_channel = interaction.guild.get_channel(log_channel_id)
            if removed_channel and isinstance(removed_channel, discord.TextChannel):
                try:
                    await removed_channel.send(embed=log_embed)
                except discord.Forbidden:
                    print(f"Could not send removal log to removed channel {log_channel_id}.")
            else:
                print(f"Log channel {log_channel_id} not found or not a text channel for removal log.")
        else:
            await interaction.response.send_message("No moderation log channel is currently set.", ephemeral=True)
    else:
        await interaction.response.send_message("No moderation log channel is currently set for this server.", ephemeral=True)

@bot.tree.command(name="perm-add", description="Adds a custom role permission to use a specific command. (Administrator Only)")
@app_commands.describe(
    role="The role to grant permission to",
    command_name="The name of the command (e.g., 'kick')"
)
async def perm_add(interaction: discord.Interaction, role: discord.Role, command_name: str):
    # This command itself must always be restricted to Discord administrators
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command. Only administrators can use /perm-add.", ephemeral=True)
        return

    command_name = command_name.lower() # Ensure command name is lowercase for consistency

    valid_commands = set()
    for cmd in bot.commands: # For prefix commands
        valid_commands.add(cmd.name)
    for cmd in bot.tree.walk_commands(): # For slash commands
        valid_commands.add(cmd.name)

    # This list now contains *only* commands that should NEVER be delegated,
    # such as the /perm-add command itself, or any fundamental bot setup commands.
    strictly_admin_commands = ["perm-add", "set-log-channel", "remove-log-channel", "appeal-form", "config", "sync"] 
    
    if command_name not in valid_commands or command_name in strictly_admin_commands:
        await interaction.response.send_message(
            f"Invalid command name '{command_name}' or this command cannot have custom role permissions. "
            "Please choose a valid command that's safe to delegate (e.g., 'warn', 'kick', 'mute', 'ban', etc.).",
            ephemeral=True
        )
        return

    guild_id_str = str(interaction.guild.id)
    if guild_id_str not in bot.config["guild_configs"]:
        bot.config["guild_configs"][guild_id_str] = {
            "log_channel_id": None,
            "log_settings": {},
            "command_permissions": {}
        }
    
    guild_config = bot.config["guild_configs"][guild_id_str]
    if "command_permissions" not in guild_config:
        guild_config["command_permissions"] = {}

    if command_name not in guild_config["command_permissions"]:
        guild_config["command_permissions"][command_name] = []

    if role.id in guild_config["command_permissions"][command_name]:
        await interaction.response.send_message(f"Role {role.mention} already has permission for command `{command_name}`.", ephemeral=True)
        return

    guild_config["command_permissions"][command_name].append(role.id)
    save_config() # Save the updated config

    embed = discord.Embed(
        title="Permission Added",
        description=f"Successfully granted role {role.mention} permission to use command `{command_name}`.",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Moderator: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

    # --- LOGGING (Optional, but good for admin actions) ---
    log_embed = discord.Embed(
        title="Command Permission Added",
        description=f"**Command:** `{command_name}`\n"
                    f"**Role:** {role.mention} (`{role.id}`)\n"
                    f"**By:** {interaction.user.mention} (`{interaction.user.display_name}` / (`{interaction.user.id}`)",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    log_embed.set_footer(text=f"Server: {interaction.guild.name}")
    await send_log_embed(interaction.guild, "config_change", log_embed)


# --- WARNING COMMANDS ---
@bot.command(name="warn", help="Warns a member. (Administrator or Custom Permission)")
async def warn(ctx, member: discord.Member = None, *, reason: str = "no reason provided"):
    if not await check_command_permission(ctx, "warn"):
        await ctx.send("You don't have permission to use this command.")
        return

    if member is None:
        usage_embed = discord.Embed(
            title="Command Usage: `$warn`",
            description="```\n$warn @user [reason]\n```\n"
                        "**Example:** `$warn @TroubleMaker Being disruptive`",
            color=0x00def1
        )
        await ctx.send(embed=usage_embed)
        return

    if member.id == ctx.author.id:
        await ctx.send("You cannot warn yourself.")
        return
    if member.id == bot.user.id:
        await ctx.send("I cannot warn myself.")
        return
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("My role is not high enough to warn this member.")
        return
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("Your role is not high enough to warn this member.")
        return

    guild_id_str = str(ctx.guild.id)
    if guild_id_str not in bot.warnings:
        bot.warnings[guild_id_str] = {}
    if str(member.id) not in bot.warnings[guild_id_str]:
        bot.warnings[guild_id_str][str(member.id)] = []

    warning_id = len(bot.warnings[guild_id_str][str(member.id)]) + 1
    timestamp = datetime.now(timezone.utc).isoformat()
    bot.warnings[guild_id_str][str(member.id)].append({
        "id": warning_id,
        "moderator_id": ctx.author.id,
        "reason": reason,
        "timestamp": timestamp
    })
    save_warnings()

    embed = discord.Embed(
        title="User Warned",
        description=f"⚠️ {member.mention} has been warned for: `{reason}`\n"
                    f"They now have {len(bot.warnings[guild_id_str][str(member.id)])} warning(s).",
        color=0x00def1
    )
    await ctx.send(embed=embed)

    # --- LOGGING ---
    log_embed = discord.Embed(
        title="User Warned",
        description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                    f"**Moderator:** {ctx.author.mention} (`{ctx.author.display_name}` / (`{ctx.author.id}`)\n"
                    f"**Reason:** {reason}\n"
                    f"**Warning ID:** {warning_id}\n"
                    f"**Total Warnings:** {len(bot.warnings[guild_id_str][str(member.id)])}",
        color=discord.Color.yellow(),
        timestamp=datetime.now(timezone.utc)
    )
    log_embed.set_thumbnail(url=member.display_avatar.url)
    log_embed.set_footer(text=f"Server: {ctx.guild.name}")
    await send_log_embed(ctx.guild, "warn", log_embed)


@bot.tree.command(name="warn", description="Warns a member.")
@app_commands.describe(member="The member to warn", reason="The reason for the warning")
async def warn_slash(interaction: discord.Interaction, member: discord.Member, reason: str):
    if not await check_command_permission(interaction, "warn"):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    if member.id == interaction.user.id:
        await interaction.response.send_message("You cannot warn yourself.", ephemeral=True)
        return
    if member.id == bot.user.id:
        await interaction.response.send_message("I cannot warn myself.", ephemeral=True)
        return
    if interaction.guild.me.top_role <= member.top_role:
        await interaction.response.send_message("My role is not high enough to warn this member.", ephemeral=True)
        return
    if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("Your role is not high enough to warn this member.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    guild_id_str = str(interaction.guild.id)
    if guild_id_str not in bot.warnings:
        bot.warnings[guild_id_str] = {}
    if str(member.id) not in bot.warnings[guild_id_str]:
        bot.warnings[guild_id_str][str(member.id)] = []

    warning_id = len(bot.warnings[guild_id_str][str(member.id)]) + 1
    timestamp = datetime.now(timezone.utc).isoformat()
    bot.warnings[guild_id_str][str(member.id)].append({
        "id": warning_id,
        "moderator_id": interaction.user.id,
        "reason": reason,
        "timestamp": timestamp
    })
    save_warnings()

    embed = discord.Embed(
        title="User Warned",
        description=f"⚠️ {member.mention} has been warned for: `{reason}`\n"
                    f"They now have {len(bot.warnings[guild_id_str][str(member.id)])} warning(s).",
        color=0x00def1
    )
    await interaction.followup.send(embed=embed)

    # --- LOGGING ---
    log_embed = discord.Embed(
        title="User Warned",
        description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                    f"**Moderator:** {interaction.user.mention} (`{interaction.user.display_name}` / (`{interaction.user.id}`)\n"
                    f"**Reason:** {reason}\n"
                    f"**Warning ID:** {warning_id}\n"
                    f"**Total Warnings:** {len(bot.warnings[guild_id_str][str(member.id)])}",
        color=discord.Color.yellow(),
        timestamp=datetime.now(timezone.utc)
    )
    log_embed.set_thumbnail(url=member.display_avatar.url)
    log_embed.set_footer(text=f"Server: {interaction.guild.name}")
    await send_log_embed(interaction.guild, "warn", log_embed)


@bot.command(name="warnings", aliases=["warns"], help="Shows warnings for a member. (Administrator or Custom Permission)")
async def warnings(ctx, member: discord.Member = None):
    if not await check_command_permission(ctx, "warnings"):
        await ctx.send("You don't have permission to use this command.")
        return

    if member is None:
        usage_embed = discord.Embed(
            title="Command Usage: `$warnings`",
            description="```\n$warnings @user\n```\n"
                        "**Example:** `$warnings @TroubleMaker`\n"
                        "Shows all warnings for the specified user.",
            color=0x00def1
        )
        await ctx.send(embed=usage_embed)
        return

    target_member = member
    guild_id_str = str(ctx.guild.id)
    member_id_str = str(target_member.id)

    if guild_id_str not in bot.warnings or member_id_str not in bot.warnings[guild_id_str]:
        await ctx.send(f"{target_member.display_name} has no warnings.")
        return

    member_warnings = bot.warnings[guild_id_str][member_id_str]
    if not member_warnings:
        await ctx.send(f"{target_member.display_name} has no warnings.")
        return

    embed = discord.Embed(
        title=f"Warnings for {target_member.display_name}",
        description=f"Total warnings: {len(member_warnings)}\n\n",
        color=0x00def1
    )
    embed.set_thumbnail(url=target_member.display_avatar.url)

    for warning in member_warnings:
        moderator = ctx.guild.get_member(warning["moderator_id"])
        moderator_name = moderator.display_name if moderator else "Unknown User"
        
        timestamp_dt = datetime.fromisoformat(warning["timestamp"])
        human_readable_time = human_timedelta(timestamp_dt)

        embed.add_field(
            name=f"Warning ID: {warning['id']}",
            value=f"**Reason:** {warning['reason']}\n"
                  f"**Moderator:** {moderator_name}\n"
                  f"**Time:** {human_readable_time}",
            inline=False
        )
    await ctx.send(embed=embed)


@bot.tree.command(name="warnings", description="Shows warnings for a member.")
@app_commands.describe(member="The member to view warnings for (defaults to yourself)")
async def warnings_slash(interaction: discord.Interaction, member: discord.Member = None):
    if not await check_command_permission(interaction, "warnings"):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    target_member = member if member else interaction.user
    guild_id_str = str(interaction.guild.id)
    member_id_str = str(target_member.id)

    if guild_id_str not in bot.warnings or member_id_str not in bot.warnings[guild_id_str]:
        await interaction.response.send_message(f"{target_member.display_name} has no warnings.", ephemeral=True)
        return

    member_warnings = bot.warnings[guild_id_str][member_id_str]
    if not member_warnings:
        await interaction.response.send_message(f"{target_member.display_name} has no warnings.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"Warnings for {target_member.display_name}",
        description=f"Total warnings: {len(member_warnings)}\n\n",
        color=0x00def1
    )
    embed.set_thumbnail(url=target_member.display_avatar.url)

    for warning in member_warnings:
        moderator = interaction.guild.get_member(warning["moderator_id"])
        moderator_name = moderator.display_name if moderator else "Unknown User"
        
        timestamp_dt = datetime.fromisoformat(warning["timestamp"])
        human_readable_time = human_timedelta(timestamp_dt)

        embed.add_field(
            name=f"Warning ID: {warning['id']}",
            value=f"**Reason:** {warning['reason']}\n"
                  f"**Moderator:** {moderator_name}\n"
                  f"**Time:** {human_readable_time}",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.command(name="delwarn", help="Deletes a specific warning for a member using a dropdown menu. (Administrator or Custom Permission)")
async def delwarn(ctx, member: discord.Member = None):
    if not await check_command_permission(ctx, "delwarn"):
        await ctx.send("You don't have permission to use this command.")
        return

    if member is None:
        usage_embed = discord.Embed(
            title="Command Usage: `$delwarn`",
            description="```\n$delwarn @user\n```\n"
                        "**Example:** `$delwarn @TroubleMaker`\n"
                        "This will open a dropdown menu to select which warning to delete.",
            color=0x00def1
        )
        await ctx.send(embed=usage_embed)
        return

    guild_id_str = str(ctx.guild.id)
    member_id_str = str(member.id)

    if guild_id_str not in bot.warnings or member_id_str not in bot.warnings[guild_id_str] or not bot.warnings[guild_id_str][member_id_str]:
        await ctx.send(f"{member.display_name} has no warnings to delete.")
        return

    warnings_list = bot.warnings[guild_id_str][member_id_str]
    
    if not warnings_list:
        await ctx.send(f"{member.display_name} has no warnings to delete.")
        return
    
    # Create the view with dropdown
    view = WarningDeleteView(member, warnings_list, ctx.author, ctx.guild)
    
    embed = discord.Embed(
        title=f"Delete Warning for {member.display_name}",
        description=f"Select a warning to delete from the dropdown menu below.\n"
                    f"**Total warnings:** {len(warnings_list)}\n\n"
                    f"⚠️ This action cannot be undone!",
        color=0x00def1
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="This menu will timeout in 60 seconds.")
    
    await ctx.send(embed=embed, view=view)


class WarningDeleteView(View):
    def __init__(self, member: discord.Member, warnings_list: list, moderator: discord.Member, guild: discord.Guild):
        super().__init__(timeout=60)
        self.member = member
        self.warnings_list = warnings_list
        self.moderator = moderator
        self.guild = guild
        
        # Create the dropdown
        self.warning_select = WarningSelect(warnings_list, member)
        self.add_item(self.warning_select)
    
    async def on_timeout(self):
        # Disable all items when the view times out
        for item in self.children:
            item.disabled = True

class WarningSelect(Select):
    def __init__(self, warnings_list: list, member: discord.Member):
        self.member = member
        self.warnings_list = warnings_list
        
        # Create options for each warning
        options = []
        for warning in warnings_list[:25]:  # Discord limit of 25 options
            moderator_id = warning.get("moderator_id", "Unknown")
            reason = warning.get("reason", "No reason")
            timestamp = warning.get("timestamp", "")
            
            # Truncate reason if too long for display
            display_reason = reason[:50] + "..." if len(reason) > 50 else reason
            
            # Format timestamp
            try:
                timestamp_dt = datetime.fromisoformat(timestamp)
                time_str = human_timedelta(timestamp_dt)
            except:
                time_str = "Unknown time"
            
            options.append(discord.SelectOption(
                label=f"Warning #{warning['id']}",
                description=f"{display_reason} • {time_str}",
                value=str(warning['id'])
            ))
        
        super().__init__(
            placeholder="Select a warning to delete...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        warning_id = int(self.values[0])
        
        # Create a modal for deletion reason
        modal = WarningDeleteModal(self.member, warning_id, self.warnings_list)
        await interaction.response.send_modal(modal)

class WarningDeleteModal(discord.ui.Modal, title="Delete Warning"):
    def __init__(self, member: discord.Member, warning_id: int, warnings_list: list):
        super().__init__()
        self.member = member
        self.warning_id = warning_id
        self.warnings_list = warnings_list
    
    reason = discord.ui.TextInput(
        label="Reason for deleting this warning",
        placeholder="Enter the reason for deleting this warning...",
        default="No reason provided",
        required=True,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        guild_id_str = str(interaction.guild.id)
        member_id_str = str(self.member.id)
        
        # Re-fetch warnings to ensure data consistency
        if guild_id_str not in bot.warnings or member_id_str not in bot.warnings[guild_id_str]:
            await interaction.response.send_message("This member no longer has any warnings.", ephemeral=True)
            return
        
        warnings_list = bot.warnings[guild_id_str][member_id_str]
        original_warning_count = len(warnings_list)
        
        # Filter out the warning to be deleted
        new_warnings_list = [w for w in warnings_list if w["id"] != self.warning_id]
        
        if len(new_warnings_list) == original_warning_count:
            await interaction.response.send_message(f"Could not find warning with ID {self.warning_id} for {self.member.display_name}.", ephemeral=True)
            return
        
        # Re-assign IDs to maintain sequential order
        for i, warn_entry in enumerate(new_warnings_list):
            warn_entry["id"] = i + 1
        
        bot.warnings[guild_id_str][member_id_str] = new_warnings_list
        save_warnings()
        
        embed = discord.Embed(
            title="Warning Deleted",
            description=f"✅ Warning ID `{self.warning_id}` for {self.member.mention} has been deleted.\n"
                        f"They now have {len(new_warnings_list)} warning(s).",
            color=0x00def1
        )
        await interaction.response.send_message(embed=embed)
        
        # --- LOGGING ---
        log_embed = discord.Embed(
            title="Warning Deleted",
            description=f"**User:** {self.member.mention} (`{self.member.display_name}` / (`{self.member.id}`)\n"
                        f"**Moderator:** {interaction.user.mention} (`{interaction.user.display_name}` / (`{interaction.user.id}`)\n"
                        f"**Warning ID Removed:** {self.warning_id}\n"
                        f"**Reason:** {self.reason.value}\n"
                        f"**New Total Warnings:** {len(new_warnings_list)}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_thumbnail(url=self.member.display_avatar.url)
        log_embed.set_footer(text=f"Server: {interaction.guild.name}")
        await send_log_embed(interaction.guild, "delwarn", log_embed)


@bot.tree.command(name="delwarn", description="Deletes a specific warning for a member using a dropdown menu.")
@app_commands.describe(member="The member to delete a warning for")
async def delwarn_slash(interaction: discord.Interaction, member: discord.Member):
    if not await check_command_permission(interaction, "delwarn"):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    guild_id_str = str(interaction.guild.id)
    member_id_str = str(member.id)

    if guild_id_str not in bot.warnings or member_id_str not in bot.warnings[guild_id_str] or not bot.warnings[guild_id_str][member_id_str]:
        await interaction.response.send_message(f"{member.display_name} has no warnings to delete.", ephemeral=True)
        return

    warnings_list = bot.warnings[guild_id_str][member_id_str]
    
    if not warnings_list:
        await interaction.response.send_message(f"{member.display_name} has no warnings to delete.", ephemeral=True)
        return
    
    # Create the view with dropdown
    view = WarningDeleteView(member, warnings_list, interaction.user, interaction.guild)
    
    embed = discord.Embed(
        title=f"Delete Warning for {member.display_name}",
        description=f"Select a warning to delete from the dropdown menu below.\n"
                    f"**Total warnings:** {len(warnings_list)}\n\n"
                    f"⚠️ This action cannot be undone!",
        color=0x00def1
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="This menu will timeout in 60 seconds.")
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


# --- KICK COMMANDS ---
@bot.command(name="kick", help="Kicks a member from the server. (Administrator or Custom Permission)")
async def kick(ctx, member: discord.Member = None, *, reason: str = "no reason provided"):
    if not await check_command_permission(ctx, "kick"):
        await ctx.send("You don't have permission to use this command.")
        return

    if member is None:
        usage_embed = discord.Embed(
            title="Command Usage: `$kick`",
            description="```\n$kick @user [reason]\n```\n"
                        "**Example:** `$kick @BadActor Repeated rule breaking`",
            color=0x00def1
        )
        await ctx.send(embed=usage_embed)
        return

    if member.id == ctx.author.id:
        await ctx.send("You cannot kick yourself.")
        return
    if member.id == bot.user.id:
        await ctx.send("I cannot kick myself.")
        return
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("My role is not high enough to kick this member.")
        return
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("Your role is not high enough to kick this member.")
        return

    try:
        await member.kick(reason=reason)
        embed = discord.Embed(description=f"👢 **{member.mention} has been kicked.**", color=0x00def1)
        await ctx.send(embed=embed)

        # --- LOGGING ---
        log_embed = discord.Embed(
            title="User Kicked",
            description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                        f"**Moderator:** {ctx.author.mention} (`{ctx.author.display_name}` / (`{ctx.author.id}`)\n"
                        f"**Reason:** {reason}",
            color=discord.Color.orange(), # Orange for kick
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text=f"Server: {ctx.guild.name}")
        await send_log_embed(ctx.guild, "kick", log_embed)

    except discord.Forbidden:
        await ctx.send(embed=discord.Embed(description="I don't have permissions to kick this member. Make sure I have the 'Kick Members' permission and my role is high enough.", color=0xff0000))
    except Exception as e:
        await ctx.send(embed=discord.Embed(description=f"Failed to kick {member.display_name}. Error: {e}", color=0xff0000))


@bot.tree.command(name="kick", description="Kicks a member from the server.")
@app_commands.describe(member="The member to kick", reason="The reason for the kick")
async def kick_slash(interaction: discord.Interaction, member: discord.Member, reason: str):
    if not await check_command_permission(interaction, "kick"):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    if member.id == interaction.user.id:
        await interaction.response.send_message("You cannot kick yourself.", ephemeral=True)
        return
    if member.id == bot.user.id:
        await interaction.response.send_message("I cannot kick myself.", ephemeral=True)
        return
    if interaction.guild.me.top_role <= member.top_role:
        await interaction.response.send_message("My role is not high enough to kick this member.", ephemeral=True)
        return
    if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("Your role is not high enough to kick this member.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False) # Defer the response

    try:
        await member.kick(reason=reason)
        embed = discord.Embed(description=f"👢 **{member.mention} has been kicked.**", color=0x00def1)
        await interaction.followup.send(embed=embed)

        # --- LOGGING ---
        log_embed = discord.Embed(
            title="User Kicked",
            description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                        f"**Moderator:** {interaction.user.mention} (`{interaction.user.display_name}` / (`{interaction.user.id}`)\n"
                        f"**Reason:** {reason}",
            color=discord.Color.orange(), # Orange for kick
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text=f"Server: {interaction.guild.name}")
        await send_log_embed(interaction.guild, "kick", log_embed)

    except discord.Forbidden:
        await interaction.followup.send(embed=discord.Embed(description="I don't have permissions to kick this member. Make sure I have the 'Kick Members' permission and my role is high enough.", color=0xff0000), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(embed=discord.Embed(description=f"Failed to kick {member.display_name}. Error: {e}", color=0xff0000), ephemeral=True)


# --- BAN COMMANDS ---
@bot.command(name="ban", help="Bans a member from the server. (Administrator or Custom Permission)")
async def ban(ctx, member: discord.Member = None, *, reason: str = "no reason provided"):
    if not await check_command_permission(ctx, "ban"):
        await ctx.send("You don't have permission to use this command.")
        return

    if member is None:
        usage_embed = discord.Embed(
            title="Command Usage: `$ban`",
            description="```\n$ban @user [reason]\n```\n"
                        "**Example:** `$ban @ProblemUser Permanent ban`",
            color=0x00def1
        )
        await ctx.send(embed=usage_embed)
        return

    if member.id == ctx.author.id:
        await ctx.send("You cannot ban yourself.")
        return
    if member.id == bot.user.id:
        await ctx.send("I cannot ban myself.")
        return
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("My role is not high enough to ban this member.")
        return
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("Your role is not high enough to ban this member.")
        return

    try:
        custom_message = bot.config.get("custom_ban_message")
        message_sent = False
        
        # IMPORTANT: Send the message BEFORE banning to ensure delivery
        if custom_message:
            try:
                formatted_message = custom_message.format(user=member.display_name, server=ctx.guild.name, reason=reason)
                await member.send(formatted_message)
                message_sent = True
                print(f"✅ Successfully sent custom ban message to {member.display_name}")
            except discord.Forbidden:
                print(f"❌ Failed to send DM to {member.display_name}: DMs disabled or bot blocked")
                message_sent = False
            except discord.HTTPException as e:
                print(f"❌ HTTP error sending DM to {member.display_name}: {e}")
                message_sent = False
            except Exception as e:
                print(f"❌ Unexpected error sending custom ban message to {member.display_name}: {e}")
                message_sent = False
        else:
            # Send default message
            try:
                default_message = f"You have been banned in {ctx.guild.name} for {reason}"
                await member.send(default_message)
                print(f"✅ Successfully sent default ban message to {member.display_name}")
                message_sent = True
            except discord.Forbidden:
                print(f"❌ Failed to send default DM to {member.display_name}: DMs disabled or bot blocked")
                message_sent = False
            except Exception as e:
                print(f"❌ Error sending default ban message to {member.display_name}: {e}")
                message_sent = False

        # Now ban the user after attempting to send the message
        await member.ban(reason=reason)
        action_type = "Banned"
        log_color = discord.Color.red()
        embed_desc = f"🔨 **{member.mention} has been banned.**"

        embed = discord.Embed(description=embed_desc, color=0x00def1)
        await ctx.send(embed=embed)
        
        # Send feedback message for custom ban message
        if custom_message:
            if message_sent:
                await ctx.send("Appeal format has been sent ✅")
            else:
                await ctx.send("User has DMs off. Couldn't send appeal format")

        # --- LOGGING ---
        log_embed = discord.Embed(
            title=f"User {action_type}",
            description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                        f"**Moderator:** {ctx.author.mention} (`{ctx.author.display_name}` / (`{ctx.author.id}`)\n"
                        f"**Reason:** {reason}",
            color=log_color,
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text=f"Server: {ctx.guild.name}")
        await send_log_embed(ctx.guild, "ban", log_embed)

    except discord.Forbidden:
        await ctx.send(embed=discord.Embed(description="I don't have permissions to ban this member. Make sure I have the 'Ban Members' permission and my role is high enough.", color=0xff0000))
    except Exception as e:
        await ctx.send(embed=discord.Embed(description=f"Failed to ban {member.display_name}. Error: {e}", color=0xff0000))


@bot.tree.command(name="ban", description="Bans a member from the server.")
@app_commands.describe(member="The member to ban", reason="The reason for the ban")
async def ban_slash(interaction: discord.Interaction, member: discord.Member, reason: str):
    if not await check_command_permission(interaction, "ban"):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    if member.id == interaction.user.id:
        await interaction.response.send_message("You cannot ban yourself.", ephemeral=True)
        return
    if member.id == bot.user.id:
        await interaction.response.send_message("I cannot ban myself.", ephemeral=True)
        return
    if interaction.guild.me.top_role <= member.top_role:
        await interaction.response.send_message("My role is not high enough to ban this member.", ephemeral=True)
        return
    if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("Your role is not high enough to ban this member.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        custom_message = bot.config.get("custom_ban_message")
        message_sent = False
        
        # IMPORTANT: Send the message BEFORE banning to ensure delivery
        if custom_message:
            try:
                formatted_message = custom_message.format(user=member.display_name, server=interaction.guild.name, reason=reason)
                await member.send(formatted_message)
                message_sent = True
                print(f"✅ Successfully sent custom ban message to {member.display_name}")
            except discord.Forbidden:
                print(f"❌ Failed to send DM to {member.display_name}: DMs disabled or bot blocked")
                message_sent = False
            except discord.HTTPException as e:
                print(f"❌ HTTP error sending DM to {member.display_name}: {e}")
                message_sent = False
            except Exception as e:
                print(f"❌ Unexpected error sending custom ban message to {member.display_name}: {e}")
                message_sent = False
        else:
            # Send default message
            try:
                default_message = f"You have been banned in {interaction.guild.name} for {reason}"
                await member.send(default_message)
                print(f"✅ Successfully sent default ban message to {member.display_name}")
                message_sent = True
            except discord.Forbidden:
                print(f"❌ Failed to send default DM to {member.display_name}: DMs disabled or bot blocked")
                message_sent = False
            except Exception as e:
                print(f"❌ Error sending default ban message to {member.display_name}: {e}")
                message_sent = False

        # Now ban the user after attempting to send the message
        await member.ban(reason=reason)
        action_type = "Banned"
        log_color = discord.Color.red()
        embed_desc = f"🔨 **{member.mention} has been banned.**"

        embed = discord.Embed(description=embed_desc, color=0x00def1)
        await interaction.followup.send(embed=embed)
        
        # Send feedback message for custom ban message
        if custom_message:
            if message_sent:
                await interaction.followup.send("Appeal format has been sent ✅")
            else:
                await interaction.followup.send("User has DMs off. Couldn't send appeal format")

        # --- LOGGING ---
        log_embed = discord.Embed(
            title=f"User {action_type}",
            description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                        f"**Moderator:** {interaction.user.mention} (`{interaction.user.display_name}` / (`{interaction.user.id}`)\n"
                        f"**Reason:** {reason}",
            color=log_color,
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text=f"Server: {interaction.guild.name}")
        await send_log_embed(interaction.guild, "ban", log_embed)

    except discord.Forbidden:
        await interaction.followup.send(embed=discord.Embed(description="I don't have permissions to ban this member. Make sure I have the 'Ban Members' permission and my role is high enough.", color=0xff0000), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(embed=discord.Embed(description=f"Failed to ban {member.display_name}. Error: {e}", color=0xff0000), ephemeral=True)


@bot.command(name="unban", help="Unbans a user by their ID. (Administrator or Custom Permission)")
async def unban(ctx, user_id: int = None, *, reason: str = "no reason provided"):
    if not await check_command_permission(ctx, "unban"):
        await ctx.send("You don't have permission to use this command.")
        return

    if user_id is None:
        usage_embed = discord.Embed(
            title="Command Usage: `$unban`",
            description="```\n$unban <user_id> [reason]\n```\n"
                        "**Example:** `$unban 123456789012345678 Appeal approved`",
            color=0x00def1
        )
        await ctx.send(embed=usage_embed)
        return

    try:
        user = await bot.fetch_user(user_id)
        if user is None:
            await ctx.send("User not found or invalid ID.")
            return

        banned_users = [entry async for entry in ctx.guild.bans()]
        found_ban = False
        for ban_entry in banned_users:
            if ban_entry.user.id == user_id:
                await ctx.guild.unban(user, reason=reason)
                found_ban = True
                break

        if found_ban:
            embed = discord.Embed(description=f"✅ **{user.mention} (`{user.id}`) has been unbanned.**", color=0x00def1)
            await ctx.send(embed=embed)

            # --- LOGGING ---
            log_embed = discord.Embed(
                title="User Unbanned",
                description=f"**User:** {user.mention} (`{user.id}`)\n"
                            f"**Moderator:** {ctx.author.mention} (`{ctx.author.display_name}` / (`{ctx.author.id}`)\n"
                            f"**Reason:** {reason}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.set_thumbnail(url=user.display_avatar.url)
            log_embed.set_footer(text=f"Server: {ctx.guild.name}")
            await send_log_embed(ctx.guild, "unban", log_embed)
        else:
            await ctx.send(embed=discord.Embed(description=f"{user.mention} is not currently banned from this server.", color=0x00def1))

    except discord.Forbidden:
        await ctx.send(embed=discord.Embed(description="I don't have permissions to unban users. Make sure I have the 'Ban Members' permission.", color=0xff0000))
    except Exception as e:
        await ctx.send(embed=discord.Embed(description=f"Failed to unban user. Error: {e}", color=0xff0000))


@bot.tree.command(name="unban", description="Unbans a user by their ID.")
@app_commands.describe(user_id="The ID of the user to unban", reason="The reason for the unban")
async def unban_slash(interaction: discord.Interaction, user_id: str, reason: str):
    if not await check_command_permission(interaction, "unban"):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    try:
        user_id_int = int(user_id)
    except ValueError:
        await interaction.response.send_message("Invalid User ID. Please provide a numeric ID.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        user = await bot.fetch_user(user_id_int)
        if user is None:
            await interaction.followup.send("User not found or invalid ID.", ephemeral=True)
            return

        banned_users = [entry async for entry in interaction.guild.bans()]
        found_ban = False
        for ban_entry in banned_users:
            if ban_entry.user.id == user_id_int:
                await interaction.guild.unban(user, reason=reason)
                found_ban = True
                break

        if found_ban:
            embed = discord.Embed(description=f"✅ **{user.mention} (`{user.id}`) has been unbanned.**", color=0x00def1)
            await interaction.followup.send(embed=embed)

            # --- LOGGING ---
            log_embed = discord.Embed(
                title="User Unbanned",
                description=f"**User:** {user.mention} (`{user.id}`)\n"
                            f"**Moderator:** {interaction.user.mention} (`{interaction.user.display_name}` / (`{interaction.user.id}`)\n"
                            f"**Reason:** {reason}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.set_thumbnail(url=user.display_avatar.url)
            log_embed.set_footer(text=f"Server: {interaction.guild.name}")
            await send_log_embed(interaction.guild, "unban", log_embed)
        else:
            await interaction.followup.send(embed=discord.Embed(description=f"{user.mention} is not currently banned from this server.", color=0x00def1), ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send(embed=discord.Embed(description="I don't have permissions to unban users. Make sure I have the 'Ban Members' permission.", color=0xff0000), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(embed=discord.Embed(description=f"Failed to unban user. Error: {e}", color=0xff0000), ephemeral=True)

# --- MUTE/UNMUTE COMMANDS (Using Discord's Timeout Feature - NO MUTE ROLE NEEDED) ---
@bot.command(name="mute", help="Mutes a member using Discord's timeout feature. (Administrator or Custom Permission)")
async def mute(ctx, member: discord.Member = None, duration: str = None, *, reason: str = "no reason provided"):
    if not await check_command_permission(ctx, "mute"):
        await ctx.send("You don't have permission to use this command.")
        return

    if member is None or duration is None:
        usage_embed = discord.Embed(
            title="Command Usage: `$mute`",
            description="```\n$mute @user <duration> [reason]\n```\n"
                        "**Examples:**\n"
                        "`$mute @Papi 10m spamming` (Mute for 10 minutes)\n"
                        "`$mute @Papi 1d rule breaking` (Mute for 1 day)\n"
                        "Supported durations: `s` (seconds), `m` (minutes), `h` (hours), `d` (days), `w` (weeks).\n"
                        "Maximum timeout duration is 28 days (4 weeks).",
            color=0x00def1
        )
        await ctx.send(embed=usage_embed)
        return

    if member.id == ctx.author.id:
        await ctx.send("You cannot mute yourself.")
        return
    if member.id == bot.user.id:
        await ctx.send("I cannot mute myself.")
        return
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("My role is not high enough to mute this member.")
        return
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("Your role is not high enough to mute this member.")
        return

    timedelta_duration = parse_duration(duration)
    if not timedelta_duration:
        await ctx.send("Invalid duration format. Use '10m', '2h', '1d', '4w'.")
        return
    
    if timedelta_duration > timedelta(days=28):
        await ctx.send("The maximum duration for a timeout is 28 days (4 weeks). Please provide a shorter duration.")
        return
            
    try:
        timeout_until = datetime.now(timezone.utc) + timedelta_duration
        await member.timeout(timeout_until, reason=reason)
        action_type = "Timed Out"
        log_color = discord.Color.red()
        embed_desc = f"🔇 **{member.mention} has been timed out for {duration}.**"

        embed = discord.Embed(description=embed_desc, color=0x00def1)
        await ctx.send(embed=embed)

        # --- LOGGING ---
        log_embed = discord.Embed(
            title=f"User {action_type}",
            description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                        f"**Moderator:** {ctx.author.mention} (`{ctx.author.display_name}` / (`{ctx.author.id}`)\n"
                        f"**Duration:** {duration.capitalize()}\n"
                        f"**Reason:** {reason}",
            color=log_color,
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text=f"Server: {ctx.guild.name}")
        await send_log_embed(ctx.guild, "mute", log_embed)

    except discord.Forbidden:
        await ctx.send(embed=discord.Embed(description="I don't have permissions to timeout this member. Make sure my role is high enough and I have the 'Moderate Members' permission.", color=0xff0000))
    except Exception as e:
        await ctx.send(embed=discord.Embed(description=f"Failed to timeout {member.display_name}. Error: {e}", color=0xff0000))


@bot.tree.command(name="mute", description="Mutes a member using Discord's timeout feature.")
@app_commands.describe(
    member="The member to mute",
    duration="Duration (e.g., '10m', '2h', '1d', '4w'). Max 28 days.",
    reason="The reason for the mute"
)
async def mute_slash(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str):
    if not await check_command_permission(interaction, "mute"):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    if member.id == interaction.user.id:
        await interaction.response.send_message("You cannot mute yourself.", ephemeral=True)
        return
    if member.id == bot.user.id:
        await interaction.response.send_message("I cannot mute myself.", ephemeral=True)
        return
    if interaction.guild.me.top_role <= member.top_role:
        await interaction.response.send_message("My role is not high enough to mute this member.", ephemeral=True)
        return
    if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("Your role is not high enough to mute this member.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    timedelta_duration = parse_duration(duration)
    if not timedelta_duration:
        await interaction.followup.send("Invalid duration format. Use '10m', '2h', '1d', '4w'.", ephemeral=True)
        return
    
    if timedelta_duration > timedelta(days=28):
        await interaction.followup.send("The maximum duration for a timeout is 28 days (4 weeks). Please provide a shorter duration.", ephemeral=True)
        return

    try:
        timeout_until = datetime.now(timezone.utc) + timedelta_duration
        await member.timeout(timeout_until, reason=reason)
        action_type = "Timed Out"
        log_color = discord.Color.red()
        embed_desc = f"🔇 **{member.mention} has been timed out for {duration}.**"

        embed = discord.Embed(description=embed_desc, color=0x00def1)
        await interaction.followup.send(embed=embed)

        # --- LOGGING ---
        log_embed = discord.Embed(
            title=f"User {action_type}",
            description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                        f"**Moderator:** {interaction.user.mention} (`{interaction.user.display_name}` / (`{interaction.user.id}`)\n"
                        f"**Duration:** {duration.capitalize()}\n"
                        f"**Reason:** {reason}",
            color=log_color,
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text=f"Server: {interaction.guild.name}")
        await send_log_embed(interaction.guild, "mute", log_embed)

    except discord.Forbidden:
        await interaction.followup.send(embed=discord.Embed(description="I don't have permissions to timeout this member. Make sure my role is high enough and I have the 'Moderate Members' permission.", color=0xff0000), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(embed=discord.Embed(description=f"Failed to timeout {member.display_name}. Error: {e}", color=0xff0000), ephemeral=True)


# --- UNMUTE COMMANDS ---
@bot.command(name="unmute", help="Unmutes a member by removing their timeout. (Administrator or Custom Permission)")
async def unmute(ctx, member: discord.Member = None, *, reason: str = "no reason provided"):
    if not await check_command_permission(ctx, "unmute"):
        await ctx.send("You don't have permission to use this command.")
        return

    if member is None:
        usage_embed = discord.Embed(
            title="Command Usage: `$unmute`",
            description="```\n$unmute @user [reason]\n```\n"
                        "**Example:** `$unmute @Papi appeal approved`",
            color=0x00def1
        )
        await ctx.send(embed=usage_embed)
        return

    # --- MORE ROBUST FIXED CHECK ---
    # Check if the member has a timeout set and if that timeout is still in the future.
    # member.timeout is a datetime object when a timeout is active, None otherwise.
    current_time = datetime.now(timezone.utc)
    if member.timed_out_until is None or member.timed_out_until <= current_time:
        await ctx.send(embed=discord.Embed(description=f"{member.mention} is not currently timed out.", color=0x00def1))
        return

    try:
        await member.timeout(None, reason=reason) # Set timeout to None to remove it
        embed = discord.Embed(description=f"🔊 **{member.mention} has been untimed out.**", color=0x00def1)
        await ctx.send(embed=embed)

        # --- LOGGING ---
        log_embed = discord.Embed(
            title="User Timeout Removed",
            description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                        f"**Moderator:** {ctx.author.mention} (`{ctx.author.display_name}` / (`{ctx.author.id}`)\n"
                        f"**Reason:** {reason}",
            color=discord.Color.green(),
            timestamp=current_time # Use the same current_time for logging consistency
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text=f"Server: {ctx.guild.name}")
        await send_log_embed(ctx.guild, "unmute", log_embed)

    except discord.Forbidden:
        await ctx.send(embed=discord.Embed(description="I don't have permissions to remove timeouts for this member. Make sure I have the 'Moderate Members' permission.", color=0xff0000))
    except Exception as e:
        await ctx.send(embed=discord.Embed(description=f"Failed to untimeout {member.display_name}. Error: {e}", color=0xff0000))


@bot.tree.command(name="unmute", description="Unmutes a member by removing their timeout.")
@app_commands.describe(member="The member to unmute", reason="The reason for the unmute")
async def unmute_slash(interaction: discord.Interaction, member: discord.Member, reason: str):
    if not await check_command_permission(interaction, "unmute"):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False) # Defer early to allow time for checks

    # --- MORE ROBUST FIXED CHECK ---
    # Check if the member has a timeout set and if that timeout is still in the future.
    current_time = datetime.now(timezone.utc)
    if member.timed_out_until is None or member.timed_out_until <= current_time:
        await interaction.followup.send(embed=discord.Embed(description=f"{member.mention} is not currently timed out.", color=0x00def1), ephemeral=True)
        return

    try:
        await member.timeout(None, reason=reason)
        embed = discord.Embed(description=f"🔊 **{member.mention} has been untimed out.**", color=0x00def1)
        await interaction.followup.send(embed=embed)

        # --- LOGGING ---
        log_embed = discord.Embed(
            title="User Timeout Removed",
            description=f"**User:** {member.mention} (`{member.display_name}` / (`{member.id}`)\n"
                        f"**Moderator:** {interaction.user.mention} (`{interaction.user.display_name}` / (`{interaction.user.id}`)\n"
                        f"**Reason:** {reason}",
            color=discord.Color.green(),
            timestamp=current_time # Use the same current_time for logging consistency
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text=f"Server: {interaction.guild.name}")
        await send_log_embed(interaction.guild, "unmute", log_embed)

    except discord.Forbidden:
        await interaction.followup.send(embed=discord.Embed(description="I don't have permissions to remove timeouts for this member. Make sure I have the 'Moderate Members' permission.", color=0xff0000), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(embed=discord.Embed(description=f"Failed to untimeout {member.display_name}. Error: {e}", color=0xff0000), ephemeral=True)



# --- PURGE COMMANDS ---
@bot.command(name="purge", help="Deletes a specified number of messages. (Administrator or Custom Permission)")
async def purge(ctx, amount: int):
    if not await check_command_permission(ctx, "purge"):
        await ctx.send("You don't have permission to use this command.")
        return

    if amount <= 0:
        await ctx.send("Please specify a positive number of messages to delete.")
        return
    
    if amount > 100:
        await ctx.send("You can only delete up to 100 messages at a time using this command.")
        return

    try:
        deleted = await ctx.channel.purge(limit=amount + 1) # +1 to also delete the command message
        embed = discord.Embed(
            description=f"🗑️ Deleted {len(deleted) - 1} messages.", # -1 because it counts the command itself
            color=0x00def1
        )
        await ctx.send(embed=embed, delete_after=5) # Delete confirmation after 5 seconds

        # --- LOGGING ---
        log_embed = discord.Embed(
            title="Messages Purged",
            description=f"**Channel:** {ctx.channel.mention}\n"
                        f"**Moderator:** {ctx.author.mention} (`{ctx.author.id}`)\n"
                        f"**Amount:** {len(deleted) - 1} messages",
            color=discord.Color.light_grey(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_footer(text=f"Server: {ctx.guild.name}")
        await send_log_embed(ctx.guild, "purge", log_embed)

    except discord.Forbidden:
        await ctx.send("I don't have permissions to delete messages in this channel. Make sure I have 'Manage Messages' permission.", ephemeral=True)
    except Exception as e:
        await ctx.send(f"An error occurred while purging messages: {e}", ephemeral=True)


@bot.tree.command(name="purge", description="Deletes a specified number of messages.")
@app_commands.describe(amount="The number of messages to delete (1-100)")
async def purge_slash(interaction: discord.Interaction, amount: int):
    if not await check_command_permission(interaction, "purge"):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("Please specify a positive number of messages to delete.", ephemeral=True)
        return
    
    if amount > 100:
        await interaction.response.send_message("You can only delete up to 100 messages at a time using this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = await interaction.channel.purge(limit=amount)
        embed = discord.Embed(
            description=f"🗑️ Deleted {len(deleted)} messages.",
            color=0x00def1
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

        # --- LOGGING ---
        log_embed = discord.Embed(
            title="Messages Purged",
            description=f"**Channel:** {interaction.channel.mention}\n"
                        f"**Moderator:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                        f"**Amount:** {len(deleted)} messages",
            color=discord.Color.light_grey(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_footer(text=f"Server: {interaction.guild.name}")
        await send_log_embed(interaction.guild, "purge", log_embed)

    except discord.Forbidden:
        await interaction.followup.send("I don't have permissions to delete messages in this channel. Make sure I have 'Manage Messages' permission.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An error occurred while purging messages: {e}", ephemeral=True)


# --- UTILITY COMMANDS (AVAILABLE TO EVERYONE) ---

@bot.command(name="serverinfo", aliases=["server"], help="Shows information about the server.")
async def serverinfo(ctx):
    guild = ctx.guild
    
    # Count members by status
    online = sum(1 for member in guild.members if member.status == discord.Status.online)
    idle = sum(1 for member in guild.members if member.status == discord.Status.idle)
    dnd = sum(1 for member in guild.members if member.status == discord.Status.dnd)
    offline = sum(1 for member in guild.members if member.status == discord.Status.offline)
    
    # Count channels
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)
    
    # Get boost info
    boost_level = guild.premium_tier
    boost_count = guild.premium_subscription_count
    
    embed = discord.Embed(
        title=f"Server Information - {guild.name}",
        color=0x00def1,
        timestamp=datetime.now(timezone.utc)
    )
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(
        name="📊 General Info",
        value=f"**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n"
              f"**Created:** {guild.created_at.strftime('%B %d, %Y')}\n"
              f"**Server ID:** {guild.id}\n"
              f"**Verification Level:** {str(guild.verification_level).title()}",
        inline=False
    )
    
    embed.add_field(
        name="👥 Members",
        value=f"**Total:** {guild.member_count}\n"
              f"🟢 Online: {online}\n"
              f"🟡 Idle: {idle}\n"
              f"🔴 DND: {dnd}\n"
              f"⚫ Offline: {offline}",
        inline=True
    )
    
    embed.add_field(
        name="📺 Channels",
        value=f"**Text:** {text_channels}\n"
              f"**Voice:** {voice_channels}\n"
              f"**Categories:** {categories}\n"
              f"**Total:** {text_channels + voice_channels}",
        inline=True
    )
    
    embed.add_field(
        name="✨ Nitro Boosts",
        value=f"**Level:** {boost_level}\n"
              f"**Boosts:** {boost_count}\n"
              f"**Roles:** {len(guild.roles)}\n"
              f"**Emojis:** {len(guild.emojis)}",
        inline=True
    )
    
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.tree.command(name="serverinfo", description="Shows information about the server.")
async def serverinfo_slash(interaction: discord.Interaction):
    guild = interaction.guild
    
    # Count members by status
    online = sum(1 for member in guild.members if member.status == discord.Status.online)
    idle = sum(1 for member in guild.members if member.status == discord.Status.idle)
    dnd = sum(1 for member in guild.members if member.status == discord.Status.dnd)
    offline = sum(1 for member in guild.members if member.status == discord.Status.offline)
    
    # Count channels
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)
    
    # Get boost info
    boost_level = guild.premium_tier
    boost_count = guild.premium_subscription_count
    
    embed = discord.Embed(
        title=f"Server Information - {guild.name}",
        color=0x00def1,
        timestamp=datetime.now(timezone.utc)
    )
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(
        name="📊 General Info",
        value=f"**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n"
              f"**Created:** {guild.created_at.strftime('%B %d, %Y')}\n"
              f"**Server ID:** {guild.id}\n"
              f"**Verification Level:** {str(guild.verification_level).title()}",
        inline=False
    )
    
    embed.add_field(
        name="👥 Members",
        value=f"**Total:** {guild.member_count}\n"
              f"🟢 Online: {online}\n"
              f"🟡 Idle: {idle}\n"
              f"🔴 DND: {dnd}\n"
              f"⚫ Offline: {offline}",
        inline=True
    )
    
    embed.add_field(
        name="📺 Channels",
        value=f"**Text:** {text_channels}\n"
              f"**Voice:** {voice_channels}\n"
              f"**Categories:** {categories}\n"
              f"**Total:** {text_channels + voice_channels}",
        inline=True
    )
    
    embed.add_field(
        name="✨ Nitro Boosts",
        value=f"**Level:** {boost_level}\n"
              f"**Boosts:** {boost_count}\n"
              f"**Roles:** {len(guild.roles)}\n"
              f"**Emojis:** {len(guild.emojis)}",
        inline=True
    )
    
    embed.set_footer(text=f"Requested by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@bot.command(name="avatar", aliases=["av"], help="Shows a user's avatar.")
async def avatar(ctx, member: discord.Member = None):
    target = member if member else ctx.author
    
    embed = discord.Embed(
        title=f"{target.display_name}'s Avatar",
        color=0x00def1,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.set_image(url=target.display_avatar.url)
    
    # Add links for different formats
    avatar_url = target.display_avatar.url
    embed.add_field(
        name="🔗 Links",
        value=f"[PNG]({avatar_url.replace('.webp', '.png')}?size=1024) | "
              f"[JPG]({avatar_url.replace('.webp', '.jpg')}?size=1024) | "
              f"[WEBP]({avatar_url}?size=1024)",
        inline=False
    )
    
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.tree.command(name="avatar", description="Shows a user's avatar.")
@app_commands.describe(member="The member to view avatar for (defaults to yourself)")
async def avatar_slash(interaction: discord.Interaction, member: discord.Member = None):
    target = member if member else interaction.user
    
    embed = discord.Embed(
        title=f"{target.display_name}'s Avatar",
        color=0x00def1,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.set_image(url=target.display_avatar.url)
    
    # Add links for different formats
    avatar_url = target.display_avatar.url
    embed.add_field(
        name="🔗 Links",
        value=f"[PNG]({avatar_url.replace('.webp', '.png')}?size=1024) | "
              f"[JPG]({avatar_url.replace('.webp', '.jpg')}?size=1024) | "
              f"[WEBP]({avatar_url}?size=1024)",
        inline=False
    )
    
    embed.set_footer(text=f"Requested by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@bot.command(name="userinfo", aliases=["user"], help="Shows information about a user.")
async def userinfo(ctx, member: discord.Member = None):
    target = member if member else ctx.author
    
    # Get roles (excluding @everyone)
    roles = [role.mention for role in target.roles[1:]]
    roles_display = ", ".join(roles[:10]) if roles else "No roles"
    if len(roles) > 10:
        roles_display += f" (+{len(roles) - 10} more)"
    
    embed = discord.Embed(
        title=f"User Information - {target.display_name}",
        color=target.color if target.color != discord.Color.default() else 0x00def1,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.set_thumbnail(url=target.display_avatar.url)
    
    embed.add_field(
        name="👤 General Info",
        value=f"**Username:** {target.name}\n"
              f"**Display Name:** {target.display_name}\n"
              f"**User ID:** {target.id}\n"
              f"**Bot:** {'Yes' if target.bot else 'No'}",
        inline=False
    )
    
    embed.add_field(
        name="📅 Dates",
        value=f"**Account Created:** {target.created_at.strftime('%B %d, %Y')}\n"
              f"**Joined Server:** {target.joined_at.strftime('%B %d, %Y') if target.joined_at else 'Unknown'}\n"
              f"**Days in Server:** {(datetime.now(timezone.utc) - target.joined_at.replace(tzinfo=timezone.utc)).days if target.joined_at else 'Unknown'}",
        inline=False
    )
    
    embed.add_field(
        name="🎭 Roles & Status",
        value=f"**Status:** {str(target.status).title()}\n"
              f"**Highest Role:** {target.top_role.mention}\n"
              f"**Role Count:** {len(target.roles) - 1}\n"
              f"**Roles:** {roles_display}",
        inline=False
    )
    
    # Add activity if present
    if target.activity:
        activity_name = target.activity.name
        activity_type = str(target.activity.type).replace('ActivityType.', '').title()
        embed.add_field(
            name="🎮 Activity",
            value=f"**{activity_type}:** {activity_name}",
            inline=False
        )
    
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.tree.command(name="userinfo", description="Shows information about a user.")
@app_commands.describe(member="The member to view info for (defaults to yourself)")
async def userinfo_slash(interaction: discord.Interaction, member: discord.Member = None):
    target = member if member else interaction.user
    
    # Get roles (excluding @everyone)
    roles = [role.mention for role in target.roles[1:]]
    roles_display = ", ".join(roles[:10]) if roles else "No roles"
    if len(roles) > 10:
        roles_display += f" (+{len(roles) - 10} more)"
    
    embed = discord.Embed(
        title=f"User Information - {target.display_name}",
        color=target.color if target.color != discord.Color.default() else 0x00def1,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.set_thumbnail(url=target.display_avatar.url)
    
    embed.add_field(
        name="👤 General Info",
        value=f"**Username:** {target.name}\n"
              f"**Display Name:** {target.display_name}\n"
              f"**User ID:** {target.id}\n"
              f"**Bot:** {'Yes' if target.bot else 'No'}",
        inline=False
    )
    
    embed.add_field(
        name="📅 Dates",
        value=f"**Account Created:** {target.created_at.strftime('%B %d, %Y')}\n"
              f"**Joined Server:** {target.joined_at.strftime('%B %d, %Y') if target.joined_at else 'Unknown'}\n"
              f"**Days in Server:** {(datetime.now(timezone.utc) - target.joined_at.replace(tzinfo=timezone.utc)).days if target.joined_at else 'Unknown'}",
        inline=False
    )
    
    embed.add_field(
        name="🎭 Roles & Status",
        value=f"**Status:** {str(target.status).title()}\n"
              f"**Highest Role:** {target.top_role.mention}\n"
              f"**Role Count:** {len(target.roles) - 1}\n"
              f"**Roles:** {roles_display}",
        inline=False
    )
    
    # Add activity if present
    if target.activity:
        activity_name = target.activity.name
        activity_type = str(target.activity.type).replace('ActivityType.', '').title()
        embed.add_field(
            name="🎮 Activity",
            value=f"**{activity_type}:** {activity_name}",
            inline=False
        )
    
    embed.set_footer(text=f"Requested by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)





# --- RUN YOUR BOT ---
if not TOKEN:
    print("Error: DISCORD_TOKEN environment variable not set!")
    print("Please add your Discord bot token to the Secrets tab.")
else:
    bot.run(TOKEN)
