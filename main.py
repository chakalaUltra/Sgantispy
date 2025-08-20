import discord
from discord.ext import commands
import asyncio
import os
from roblox_api import RobloxAPI
from threat_analyzer import ThreatAnalyzer
from config import DISCORD_CONFIG

# Bot configuration
intents = discord.Intents.default()
bot = commands.Bot(command_prefix=DISCORD_CONFIG['COMMAND_PREFIX'], intents=intents)

# Initialize APIs
roblox_api = RobloxAPI()
threat_analyzer = ThreatAnalyzer()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="checkuser", description="Analyze a Roblox user profile for suspicious patterns")
async def check_user(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    
    # Send initial status update
    status_embed = discord.Embed(
        title="🔍 Analyzing User Profile",
        description=f"Starting analysis of **{username}**...",
        color=0x3498db
    )
    status_embed.add_field(name="Status", value="📋 Fetching user profile...", inline=False)
    await interaction.edit_original_response(embed=status_embed)
    
    try:
        # Get user profile
        user_profile = await roblox_api.get_user_profile(username)
        if not user_profile:
            await interaction.followup.send(f"❌ User '{username}' not found on Roblox.")
            return
        
        user_id = user_profile['id']
        display_name = user_profile['displayName']
        created_date = user_profile['created']
        
        # Initialize analysis results
        analysis_results = {
            'user_profile': user_profile,
            'suspicious_friends': [],
            'suspicious_followers': [],
            'suspicious_following': [],
            'account_age_flag': False,
            'badge_count_flag': False,
            'specific_badges_found': [],
            'avatar_flag': False,
            'flags': []
        }
        
        # Update status - analyzing connections
        status_embed.set_field_at(0, name="Status", value="👥 Analyzing friends, followers, and following...", inline=False)
        await interaction.edit_original_response(embed=status_embed)
        
        # Analyze friends, followers, and following concurrently to reduce wait time
        print(f"Analyzing social connections for user {username}...")
        friends_task = roblox_api.get_user_friends(user_id)
        followers_task = roblox_api.get_user_followers(user_id)
        following_task = roblox_api.get_user_following(user_id)
        groups_task = roblox_api.get_user_groups(user_id)
        
        # Wait for all social data concurrently with timeout
        try:
            friends, followers, following, user_groups = await asyncio.wait_for(
                asyncio.gather(friends_task, followers_task, following_task, groups_task, return_exceptions=True),
                timeout=60  # 60 second timeout for thorough checking
            )
        except asyncio.TimeoutError:
            print("Social connections analysis timed out, proceeding with partial data...")
            friends, followers, following, user_groups = [], [], [], []
        
        # Process results
        if friends and not isinstance(friends, Exception):
            analysis_results['suspicious_friends'] = threat_analyzer.check_suspicious_names(friends)
            if analysis_results['suspicious_friends']:
                analysis_results['flags'].append("Suspicious friends detected")
        
        if followers and not isinstance(followers, Exception):
            analysis_results['suspicious_followers'] = threat_analyzer.check_suspicious_names(followers)
            if analysis_results['suspicious_followers']:
                analysis_results['flags'].append("Suspicious followers detected")
        
        if following and not isinstance(following, Exception):
            analysis_results['suspicious_following'] = threat_analyzer.check_suspicious_names(following)
            if analysis_results['suspicious_following']:
                analysis_results['flags'].append("Suspicious following detected")
        
        # Check account age
        analysis_results['account_age_flag'] = threat_analyzer.check_account_age(created_date)
        if analysis_results['account_age_flag']:
            analysis_results['flags'].append("Account younger than 4 months")
        
        # Update status - analyzing badges and avatar
        status_embed.set_field_at(0, name="Status", value="🏆 Analyzing badges and avatar...", inline=False)
        await interaction.edit_original_response(embed=status_embed)
        
        # Check badges and avatar concurrently with timeout
        print(f"Analyzing badges and avatar for user {username}...")
        badges_task = roblox_api.get_user_badges(user_id)
        avatar_task = roblox_api.get_user_avatar(user_id)
        
        try:
            user_badges, avatar_items = await asyncio.wait_for(
                asyncio.gather(badges_task, avatar_task, return_exceptions=True),
                timeout=45  # 45 second timeout for thorough badge checking
            )
        except asyncio.TimeoutError:
            print("Badges/avatar analysis timed out, proceeding with partial data...")
            user_badges, avatar_items = None, None
        
        # Process badge results
        if user_badges is not None and not isinstance(user_badges, Exception) and isinstance(user_badges, list):
            analysis_results['badge_count'] = len(user_badges)
            analysis_results['badge_count_flag'] = threat_analyzer.check_badge_count(user_badges)
            if analysis_results['badge_count_flag']:
                analysis_results['flags'].append("Less than 40 badges")
            
            analysis_results['specific_badges_found'] = threat_analyzer.check_specific_badges(user_badges)
            if analysis_results['specific_badges_found']:
                analysis_results['flags'].append("TSB badges found")
        elif user_badges is None or isinstance(user_badges, Exception):
            # Badges could not be fetched - likely hidden or API error
            analysis_results['badges_hidden'] = True
            analysis_results['flags'].append("Badges not visible")
        
        # Process avatar results
        if avatar_items is not None and not isinstance(avatar_items, Exception):
            analysis_results['avatar_flag'] = threat_analyzer.check_default_avatar(avatar_items)
            if analysis_results['avatar_flag']:
                analysis_results['flags'].append("Default/low-robux avatar")
        
        # Update status - advanced analysis
        status_embed.set_field_at(0, name="Status", value="🔬 Running advanced pattern analysis...", inline=False)
        await interaction.edit_original_response(embed=status_embed)
        
        # Run new advanced analysis features
        all_suspicious_friends = analysis_results['suspicious_friends'] + analysis_results['suspicious_followers'] + analysis_results['suspicious_following']
        
        # Feature 4: Group analysis (check shared groups)
        analysis_results['shared_groups'] = []
        if user_groups and not isinstance(user_groups, Exception) and all_suspicious_friends:
            # This would require additional API calls for each suspicious friend's groups
            # For now, we'll just store the user's groups for future enhancement
            analysis_results['user_groups'] = user_groups
        
        # Feature 5: Creation date patterns
        analysis_results['creation_date_patterns'] = []
        if all_suspicious_friends:
            # We need creation dates for suspicious friends - would require additional API calls
            # For now, we'll analyze with what we have
            friends_with_profiles = []
            for friend in all_suspicious_friends[:10]:  # Limit to 10 to avoid timeouts
                try:
                    friend_profile = await roblox_api.get_user_profile(friend['name'])
                    if friend_profile:
                        friend['created_date'] = friend_profile['created']
                        friends_with_profiles.append(friend)
                except:
                    continue
            
            if friends_with_profiles:
                creation_patterns = threat_analyzer.check_creation_date_patterns(created_date, friends_with_profiles)
                analysis_results['creation_date_patterns'] = creation_patterns
                if creation_patterns:
                    analysis_results['flags'].append(f"Account creation patterns detected ({len(creation_patterns)} accounts)")
        
        # Feature 7: Username generation patterns
        analysis_results['username_patterns'] = []
        if all_suspicious_friends:
            username_patterns = threat_analyzer.check_username_generation_patterns(all_suspicious_friends)
            analysis_results['username_patterns'] = username_patterns
            if username_patterns:
                analysis_results['flags'].append(f"Username generation patterns detected ({len(username_patterns)} patterns)")
        
        # Calculate threat level
        threat_level = threat_analyzer.calculate_threat_level(analysis_results)
        
        # Create response embed
        embed = await create_analysis_embed(analysis_results, threat_level, username, user_id)
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Error analyzing user {username}: {e}")
        await interaction.followup.send(f"❌ An error occurred while analyzing user '{username}': {str(e)}")

async def create_analysis_embed(results, threat_level, username, user_id):
    # Set embed color based on threat level from config
    colors = DISCORD_CONFIG['EMBED_COLORS']
    
    embed = discord.Embed(
        title=f"🔍 Analysis Report for {username}",
        description=f"**Threat Level: {threat_level}**",
        color=colors.get(threat_level, 0x808080),
        url=f"https://www.roblox.com/users/{user_id}/profile"
    )
    
    # Add user info
    created_date = results['user_profile']['created']
    embed.add_field(
        name="👤 User Information",
        value=f"**Display Name:** {results['user_profile']['displayName']}\n"
              f"**User ID:** {user_id}\n"
              f"**Created:** {created_date[:10]}\n"
              f"**Profile:** [View Profile](https://www.roblox.com/users/{user_id}/profile)",
        inline=False
    )
    
    # Add flags summary
    if results['flags']:
        flags_text = "\n".join([f"🚩 {flag}" for flag in results['flags']])
        embed.add_field(name="⚠️ Flags Detected", value=flags_text, inline=False)
    else:
        embed.add_field(name="✅ No Flags", value="No suspicious patterns detected", inline=False)
    
    # Add suspicious friends
    if results['suspicious_friends']:
        friends_text = ""
        for friend in results['suspicious_friends']:  # Show all friends
            friends_text += f"• [{friend['displayName']}](https://www.roblox.com/users/{friend['id']}/profile) - Pattern: {friend['matched_pattern']}\n"
        embed.add_field(name="👥 Suspicious Friends", value=friends_text, inline=False)
    
    # Add suspicious followers
    if results['suspicious_followers']:
        followers_text = ""
        for follower in results['suspicious_followers'][:3]:  # Limit to first 3
            followers_text += f"• [{follower['displayName']}](https://www.roblox.com/users/{follower['id']}/profile) - Pattern: {follower['matched_pattern']}\n"
        if len(results['suspicious_followers']) > 3:
            followers_text += f"... and {len(results['suspicious_followers']) - 3} more"
        embed.add_field(name="👤 Suspicious Followers", value=followers_text, inline=False)
    
    # Add suspicious following
    if results['suspicious_following']:
        following_text = ""
        for following in results['suspicious_following'][:3]:  # Limit to first 3
            following_text += f"• [{following['displayName']}](https://www.roblox.com/users/{following['id']}/profile) - Pattern: {following['matched_pattern']}\n"
        if len(results['suspicious_following']) > 3:
            following_text += f"... and {len(results['suspicious_following']) - 3} more"
        embed.add_field(name="👁️ Suspicious Following", value=following_text, inline=False)
    
    # Add TSB badges found
    if results['specific_badges_found']:
        badges_text = ""
        for badge in results['specific_badges_found']:
            badges_text += f"⚔️ **{badge['expected_name']}** (ID: {badge['id']})\n"
        embed.add_field(name="⚔️ TSB Badges", value=badges_text, inline=False)
    elif results.get('badges_hidden', False):
        embed.add_field(name="⚔️ TSB Badges", value="🔒 Badges not visible", inline=False)
    
    # Show badge count
    if 'badge_count' in results:
        embed.add_field(
            name="📊 Badge Statistics",
            value=f"Total badges: **{results['badge_count']}**\n{'🚩 Below 40 badges threshold' if results.get('badge_count_flag') else '✅ Above 40 badges threshold'}",
            inline=False
        )
    
    # Show creation date patterns (Feature 5)
    if results.get('creation_date_patterns'):
        patterns_text = ""
        for pattern in results['creation_date_patterns'][:5]:  # Limit to 5
            patterns_text += f"📅 **{pattern['username']}** - Created {pattern['days_apart']} days apart\n"
        if len(results['creation_date_patterns']) > 5:
            patterns_text += f"... and {len(results['creation_date_patterns']) - 5} more"
        embed.add_field(name="📅 Account Creation Patterns", value=patterns_text, inline=False)
    
    # Show username generation patterns (Feature 7)
    if results.get('username_patterns'):
        patterns_text = ""
        for pattern in results['username_patterns'][:3]:  # Limit to 3 patterns
            pattern_type = pattern['type']
            usernames = ", ".join(pattern['usernames'][:5])  # Show first 5 usernames
            if len(pattern['usernames']) > 5:
                usernames += f" (+{len(pattern['usernames']) - 5} more)"
            patterns_text += f"🤖 **{pattern_type}:** {usernames}\n"
        embed.add_field(name="🤖 Username Generation Patterns", value=patterns_text, inline=False)
    
    embed.set_footer(text="Analysis completed • Enhanced Roblox Profile Analyzer v2.0")
    
    return embed

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN environment variable not found!")
        exit(1)
    
    bot.run(token)
