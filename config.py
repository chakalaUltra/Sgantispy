# Configuration file for Roblox API and analysis settings
import os

# Helper function to parse comma-separated environment variables
def parse_env_list(env_var, default_list):
    env_value = os.getenv(env_var)
    if env_value:
        return [item.strip() for item in env_value.split(',')]
    return default_list

def parse_env_badge_ids(env_var, default_list):
    env_value = os.getenv(env_var)
    if env_value:
        try:
            return [int(item.strip()) for item in env_value.split(',')]
        except ValueError:
            print(f"Warning: Invalid badge IDs in {env_var}, using defaults")
            return default_list
    return default_list

ROBLOX_CONFIG = {
    # API endpoints
    'BASE_URL': os.getenv('ROBLOX_BASE_URL', 'https://api.roblox.com'),
    'USERS_URL': os.getenv('ROBLOX_USERS_URL', 'https://users.roblox.com'),
    'BADGES_URL': os.getenv('ROBLOX_BADGES_URL', 'https://badges.roblox.com'),
    'AVATAR_URL': os.getenv('ROBLOX_AVATAR_URL', 'https://avatar.roblox.com'),
    'FRIENDS_URL': os.getenv('ROBLOX_FRIENDS_URL', 'https://friends.roblox.com'),
    
    # Rate limiting
    'REQUEST_DELAY': float(os.getenv('ROBLOX_REQUEST_DELAY', '1.0')),
    'MAX_RETRIES': int(os.getenv('ROBLOX_MAX_RETRIES', '3')),
    
    # Analysis settings
    'MIN_BADGE_COUNT': int(os.getenv('MIN_BADGE_COUNT', '40')),
    'ACCOUNT_AGE_THRESHOLD_DAYS': int(os.getenv('ACCOUNT_AGE_THRESHOLD_DAYS', '120')),
    
    # Suspicious patterns (case insensitive)
    'SUSPICIOUS_PATTERNS': parse_env_list('SUSPICIOUS_PATTERNS', 
        ['xyris', 'vqs', 'risen', 'sc', 'dt', 'xraid']),
    
    # Specific badge IDs to check for
    'SUSPICIOUS_BADGE_IDS': parse_env_badge_ids('SUSPICIOUS_BADGE_IDS', [
        3057416426456972,  # Baby Steps
        3114670201603542,  # Head First
        3006399776257311,  # A Natural
        268490457371003,   # Turning Point
        341084106898320,   # Seasoned Killer
        2724124286915993   # Skull Seeker
    ]),
    
    # Threat level thresholds
    'THREAT_LEVELS': {
        'LOW_THRESHOLD': int(os.getenv('THREAT_LOW_THRESHOLD', '40')),
        'MEDIUM_THRESHOLD': int(os.getenv('THREAT_MEDIUM_THRESHOLD', '70'))
    }
}

# Discord bot settings
DISCORD_CONFIG = {
    'COMMAND_PREFIX': os.getenv('DISCORD_COMMAND_PREFIX', '!'),
    'EMBED_COLORS': {
        'Low': int(os.getenv('DISCORD_COLOR_LOW', '0x00ff00'), 16),      # Green
        'Medium': int(os.getenv('DISCORD_COLOR_MEDIUM', '0xffff00'), 16), # Yellow
        'High': int(os.getenv('DISCORD_COLOR_HIGH', '0xff0000'), 16)      # Red
    }
}
