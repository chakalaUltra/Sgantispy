import aiohttp
import asyncio
import json
from datetime import datetime
from config import ROBLOX_CONFIG

class RobloxAPI:
    def __init__(self):
        self.base_url = "https://api.roblox.com"
        self.users_url = "https://users.roblox.com"
        self.badges_url = "https://badges.roblox.com"
        self.avatar_url = "https://avatar.roblox.com"
        self.friends_url = "https://friends.roblox.com"
        self.groups_url = "https://groups.roblox.com"
        self.session = None
        self.rate_limit_delay = 1.5  # 1.5 seconds between requests
        self.last_request_time = 0
    
    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def _rate_limited_request(self, url, max_retries=3, **kwargs):
        """Make a rate-limited request to avoid hitting API limits"""
        await self._ensure_session()
        
        for attempt in range(max_retries):
            # Rate limiting
            current_time = asyncio.get_event_loop().time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - time_since_last)
            
            try:
                if self.session:
                    async with self.session.get(url, **kwargs) as response:
                        self.last_request_time = asyncio.get_event_loop().time()
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:  # Rate limited
                            if attempt < max_retries - 1:  # Don't wait on last attempt
                                wait_time = min(8, 2 ** attempt)  # Exponential backoff: 2, 4, 8 seconds
                                print(f"Rate limited (attempt {attempt + 1}/{max_retries}), waiting {wait_time} seconds...")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                print(f"Max retries reached for {url}, skipping...")
                                return None
                        else:
                            print(f"API request failed with status {response.status}: {url}")
                            return None
            except Exception as e:
                print(f"Request failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return None
        
        return None
    
    async def get_user_profile(self, username):
        """Get user profile by username"""
        # First get user ID by username
        url = f"{self.users_url}/v1/usernames/users"
        payload = {
            "usernames": [username],
            "excludeBannedUsers": True
        }
        
        await self._ensure_session()
        try:
            if self.session:
                async with self.session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('data') and len(data['data']) > 0:
                            user_id = data['data'][0]['id']
                            # Now get full profile
                            return await self.get_user_profile_by_id(user_id)
                    return None
        except Exception as e:
            print(f"Error getting user profile: {e}")
            return None
    
    async def get_user_profile_by_id(self, user_id):
        """Get user profile by user ID"""
        url = f"{self.users_url}/v1/users/{user_id}"
        return await self._rate_limited_request(url)
    
    async def get_user_friends(self, user_id, limit=200):
        """Get user's friends list"""
        url = f"{self.friends_url}/v1/users/{user_id}/friends"
        data = await self._rate_limited_request(url)
        if data and 'data' in data:
            return data['data']  # Return all friends for thorough checking
        return []
    
    async def get_user_followers(self, user_id, limit=100):
        """Get user's followers"""
        url = f"{self.friends_url}/v1/users/{user_id}/followers"
        params = {"limit": min(limit, 100)}  # API limit is 100
        data = await self._rate_limited_request(url, params=params)
        if data and 'data' in data:
            return data['data']
        return []
    
    async def get_user_following(self, user_id, limit=100):
        """Get users that the user is following"""
        url = f"{self.friends_url}/v1/users/{user_id}/followings"
        params = {"limit": min(limit, 100)}  # API limit is 100
        data = await self._rate_limited_request(url, params=params)
        if data and 'data' in data:
            return data['data']
        return []
    
    async def get_user_badges(self, user_id):
        """Get user's badges"""
        all_badges = []
        cursor = ""
        max_pages = 5  # Limit to 5 pages (500 badges max) for thorough checking
        
        for page in range(max_pages):
            url = f"{self.badges_url}/v1/users/{user_id}/badges"
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            
            data = await self._rate_limited_request(url, params=params)
            if not data or 'data' not in data:
                break
            
            all_badges.extend(data['data'])
            
            # Check if there are more pages
            if 'nextPageCursor' not in data or not data['nextPageCursor']:
                break
            cursor = data['nextPageCursor']
        
        return all_badges
    
    async def get_user_avatar(self, user_id):
        """Get user's avatar items"""
        url = f"{self.avatar_url}/v1/users/{user_id}/avatar"
        data = await self._rate_limited_request(url)
        if data and 'assets' in data:
            return data['assets']
        return []
    
    async def get_user_groups(self, user_id):
        """Get groups that a user is a member of"""
        url = f"{self.groups_url}/v2/users/{user_id}/groups/roles"
        data = await self._rate_limited_request(url)
        if data and 'data' in data:
            return data['data']
        return []
    
    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()
