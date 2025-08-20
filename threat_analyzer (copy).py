import re
from datetime import datetime, timedelta
from collections import defaultdict
from config import ROBLOX_CONFIG

class ThreatAnalyzer:
    def __init__(self):
        self.suspicious_patterns = [
            'xyris', 'vqs', 'risen', 'sc', 'dt', 'xraid'
        ]
        self.specific_badge_ids = {
            3057416426456972: "Baby Steps",
            3114670201603542: "Head First", 
            3006399776257311: "A Natural",
            268490457371003: "Turning Point",
            341084106898320: "Seasoned Killer",
            2724124286915993: "Skull Seeker"
        }
    
    def check_suspicious_names(self, users_list):
        """Check for suspicious name patterns in a list of users"""
        suspicious_users = []
        
        for user in users_list:
            username = user.get('name', '').lower()
            display_name = user.get('displayName', '').lower()
            
            # Check both username and display name
            for pattern in self.suspicious_patterns:
                if pattern in username or pattern in display_name:
                    user_copy = user.copy()
                    user_copy['matched_pattern'] = pattern.upper()
                    suspicious_users.append(user_copy)
                    break  # Only flag once per user
        
        return suspicious_users
    
    def check_account_age(self, created_date):
        """Check if account is younger than 4 months"""
        try:
            # Parse the created date
            if isinstance(created_date, str):
                # Handle different date formats
                if 'T' in created_date:
                    created_dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                else:
                    created_dt = datetime.strptime(created_date, '%Y-%m-%d')
            else:
                created_dt = created_date
            
            # Remove timezone info for comparison
            if created_dt.tzinfo:
                created_dt = created_dt.replace(tzinfo=None)
            
            # Calculate if account is younger than 4 months
            four_months_ago = datetime.now() - timedelta(days=120)  # Approximately 4 months
            
            return created_dt > four_months_ago
        except Exception as e:
            print(f"Error parsing date {created_date}: {e}")
            return False
    
    def check_badge_count(self, badges_list):
        """Check if user has less than 40 badges"""
        return len(badges_list) < 40
    
    def check_specific_badges(self, badges_list):
        """Check for specific suspicious badges"""
        found_badges = []
        
        for badge in badges_list:
            badge_id = badge.get('id')
            if badge_id in self.specific_badge_ids:
                found_badges.append({
                    'id': badge_id,
                    'name': badge.get('name', self.specific_badge_ids[badge_id]),
                    'description': badge.get('description', ''),
                    'expected_name': self.specific_badge_ids[badge_id]
                })
        
        return found_badges
    
    def check_default_avatar(self, avatar_items):
        """Check if user has default/low robux avatar"""
        if not avatar_items:
            return True  # No avatar items means default
        
        # Count non-free items
        paid_items = 0
        total_items = len(avatar_items)
        
        for item in avatar_items:
            asset_type = item.get('assetType', {}).get('name', '')
            # Default items are usually basic clothing, hair, etc.
            # If user has very few items or mostly default items, flag it
            if asset_type not in ['Shirt', 'Pants', 'TShirt']:
                paid_items += 1
        
        # Flag if user has very few customization items
        return total_items < 5 or paid_items < 2
    
    def calculate_threat_level(self, analysis_results):
        """Calculate overall threat level based on analysis results"""
        threat_score = 0
        max_score = 0
        
        # Weight different factors
        factors = {
            'suspicious_friends': (len(analysis_results['suspicious_friends']), 3, 2),
            'suspicious_followers': (len(analysis_results['suspicious_followers']), 2, 1),
            'suspicious_following': (len(analysis_results['suspicious_following']), 2, 1),
            'account_age_flag': (1 if analysis_results['account_age_flag'] else 0, 1, 3),
            'badge_count_flag': (1 if analysis_results['badge_count_flag'] else 0, 1, 2),
            'specific_badges_found': (len(analysis_results['specific_badges_found']), 3, 2),
            'avatar_flag': (1 if analysis_results['avatar_flag'] else 0, 1, 1)
        }
        
        for factor_name, (count, max_count, weight) in factors.items():
            factor_score = min(count / max_count, 1.0) * weight
            threat_score += factor_score
            max_score += weight
        
        # Normalize score to percentage
        if max_score > 0:
            threat_percentage = (threat_score / max_score) * 100
        else:
            threat_percentage = 0
        
        # Determine threat level
        if threat_percentage >= 70:
            return "High"
        elif threat_percentage >= 40:
            return "Medium"
        else:
            return "Low"
    
    def check_shared_groups(self, target_groups, suspicious_friends_list):
        """Check if suspicious friends share groups with the target user"""
        if not target_groups or not suspicious_friends_list:
            return []
        
        target_group_ids = {group.get('group', {}).get('id') for group in target_groups}
        shared_groups = []
        
        # This would need additional API calls for each suspicious friend
        # For now, we'll return the structure but populate it in main.py
        return shared_groups
    
    def check_creation_date_patterns(self, user_created_date, suspicious_friends_data):
        """Check if multiple accounts were created around the same time"""
        if not user_created_date or not suspicious_friends_data:
            return []
        
        try:
            if isinstance(user_created_date, str):
                if 'T' in user_created_date:
                    user_date = datetime.fromisoformat(user_created_date.replace('Z', '+00:00'))
                else:
                    user_date = datetime.strptime(user_created_date, '%Y-%m-%d')
            else:
                user_date = user_created_date
            
            if user_date.tzinfo:
                user_date = user_date.replace(tzinfo=None)
            
            same_period_accounts = []
            
            for friend_data in suspicious_friends_data:
                friend_created = friend_data.get('created_date')
                if not friend_created:
                    continue
                
                try:
                    if isinstance(friend_created, str):
                        if 'T' in friend_created:
                            friend_date = datetime.fromisoformat(friend_created.replace('Z', '+00:00'))
                        else:
                            friend_date = datetime.strptime(friend_created, '%Y-%m-%d')
                    else:
                        friend_date = friend_created
                    
                    if friend_date.tzinfo:
                        friend_date = friend_date.replace(tzinfo=None)
                    
                    # Check if accounts were created within 7 days of each other
                    time_diff = abs((user_date - friend_date).days)
                    if time_diff <= 7:
                        same_period_accounts.append({
                            'username': friend_data.get('name'),
                            'created_date': friend_created,
                            'days_apart': time_diff
                        })
                
                except Exception as e:
                    print(f"Error parsing friend creation date: {e}")
                    continue
            
            return same_period_accounts
        
        except Exception as e:
            print(f"Error checking creation date patterns: {e}")
            return []
    
    def check_username_generation_patterns(self, suspicious_friends_list):
        """Detect username patterns that suggest automated generation"""
        if not suspicious_friends_list:
            return []
        
        patterns_found = []
        usernames = [user.get('name', '') for user in suspicious_friends_list]
        
        # Pattern 1: Sequential numbers (user1, user2, user3)
        number_base_groups = defaultdict(list)
        for username in usernames:
            # Extract base name and number
            match = re.match(r'^(.+?)(\d+)$', username.lower())
            if match:
                base_name, number = match.groups()
                number_base_groups[base_name].append((username, int(number)))
        
        # Check for sequential patterns
        for base_name, user_list in number_base_groups.items():
            if len(user_list) >= 2:
                user_list.sort(key=lambda x: x[1])  # Sort by number
                numbers = [num for _, num in user_list]
                
                # Check for consecutive or near-consecutive numbers
                is_sequential = True
                for i in range(1, len(numbers)):
                    if numbers[i] - numbers[i-1] > 3:  # Allow gaps of up to 3
                        is_sequential = False
                        break
                
                if is_sequential:
                    pattern_usernames = [username for username, _ in user_list]
                    patterns_found.append({
                        'type': 'Sequential Numbers',
                        'pattern': f"{base_name}[numbers]",
                        'usernames': pattern_usernames,
                        'description': f"Sequential numbering pattern: {', '.join(pattern_usernames)}"
                    })
        
        # Pattern 2: Similar prefixes/suffixes with variations
        prefix_groups = defaultdict(list)
        suffix_groups = defaultdict(list)
        
        for username in usernames:
            username_lower = username.lower()
            # Group by first 4 characters (prefix)
            if len(username_lower) >= 4:
                prefix = username_lower[:4]
                prefix_groups[prefix].append(username)
            
            # Group by last 4 characters (suffix)
            if len(username_lower) >= 4:
                suffix = username_lower[-4:]
                suffix_groups[suffix].append(username)
        
        # Check for multiple users with same prefix/suffix
        for prefix, user_list in prefix_groups.items():
            if len(user_list) >= 3:  # 3 or more users with same prefix
                patterns_found.append({
                    'type': 'Common Prefix',
                    'pattern': f"{prefix}*",
                    'usernames': user_list,
                    'description': f"Common prefix '{prefix}': {', '.join(user_list)}"
                })
        
        for suffix, user_list in suffix_groups.items():
            if len(user_list) >= 3:  # 3 or more users with same suffix
                patterns_found.append({
                    'type': 'Common Suffix', 
                    'pattern': f"*{suffix}",
                    'usernames': user_list,
                    'description': f"Common suffix '{suffix}': {', '.join(user_list)}"
                })
        
        # Pattern 3: Character substitution patterns (0 for o, 3 for e, etc.)
        substitution_patterns = []
        for i, username1 in enumerate(usernames):
            for username2 in usernames[i+1:]:
                similarity = self._check_character_substitution_similarity(username1.lower(), username2.lower())
                if similarity > 0.8:  # 80% similar after accounting for substitutions
                    substitution_patterns.append((username1, username2))
        
        if substitution_patterns:
            unique_users = set()
            for pair in substitution_patterns:
                unique_users.update(pair)
            
            patterns_found.append({
                'type': 'Character Substitution',
                'pattern': 'Similar names with character substitutions',
                'usernames': list(unique_users),
                'description': f"Similar usernames with character substitutions: {', '.join(unique_users)}"
            })
        
        return patterns_found
    
    def _check_character_substitution_similarity(self, username1, username2):
        """Check similarity accounting for common character substitutions"""
        # Common substitutions in usernames
        substitutions = {
            '0': 'o', '1': 'i', '1': 'l', '3': 'e', '4': 'a', 
            '5': 's', '7': 't', '8': 'b', '@': 'a'
        }
        
        # Normalize both usernames by applying reverse substitutions
        def normalize_username(username):
            normalized = username
            for num, char in substitutions.items():
                normalized = normalized.replace(num, char)
            return normalized
        
        norm1 = normalize_username(username1)
        norm2 = normalize_username(username2)
        
        # Calculate similarity using simple character matching
        if len(norm1) == 0 or len(norm2) == 0:
            return 0
        
        matches = sum(1 for a, b in zip(norm1, norm2) if a == b)
        max_len = max(len(norm1), len(norm2))
        
        return matches / max_len if max_len > 0 else 0
