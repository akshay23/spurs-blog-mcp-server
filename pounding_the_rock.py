#!/usr/bin/env python3
from mcp.server.fastmcp import FastMCP, Context, Image
import httpx
import xml.etree.ElementTree as ET
import re
import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List, Union

# Initialize FastMCP server
mcp = FastMCP("Spurs Blog Assistant")

# Constants
PTR_RSS_URL = "https://www.poundingtherock.com/rss/current.xml"
USER_AGENT = "spurs-blog-assistant/1.0"

# Cache to store fetched data
article_cache = {}
player_stats_cache = {}
game_results_cache = {}
last_fetch_time = None
CACHE_DURATION = datetime.timedelta(minutes=30)  # Refresh cache every 30 minutes

@dataclass
class Article:
    """Class for storing article information."""
    title: str
    link: str
    description: str
    pub_date: str
    guid: str
    content: Optional[str] = None
    
@dataclass
class GameResult:
    """Class for storing game result information."""
    date: str
    opponent: str
    score: str
    result: str  # Win/Loss
    location: str
    
@dataclass
class PlayerInfo:
    """Class for storing player information."""
    name: str
    stats: Dict[str, Any]
    mentions: List[Dict[str, str]]  # List of article snippets mentioning the player

async def fetch_and_parse_rss():
    """Fetch and parse the RSS feed from Pounding The Rock."""
    global article_cache, last_fetch_time
    
    # Check if cache is fresh
    current_time = datetime.datetime.now()
    if last_fetch_time and (current_time - last_fetch_time) < CACHE_DURATION and article_cache:
        return article_cache
    
    async with httpx.AsyncClient() as client:
        headers = {"User-Agent": USER_AGENT}
        try:
            response = await client.get(PTR_RSS_URL, headers=headers, timeout=30.0)
            response.raise_for_status()
            
            # Parse the XML
            root = ET.fromstring(response.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            articles = []
            
            # Process Atom feed (entries instead of items)
            for entry in root.findall('atom:entry', ns):
                title = entry.find('atom:title', ns).text if entry.find('atom:title', ns) is not None else ""
                link_el = entry.find("atom:link[@rel='alternate']", ns)
                link = link_el.attrib['href'] if link_el is not None else ""
                pub_date = entry.find('atom:published', ns).text if entry.find('atom:published', ns) is not None else ""
                guid = entry.find('atom:id', ns).text if entry.find('atom:id', ns) is not None else ""
                content = entry.find('atom:content', ns).text if entry.find('atom:content', ns) is not None else ""
                
                # Generate a brief description by truncating plain text
                description = content[:200] + '...' if content else ""
                
                articles.append(Article(
                    title=title,
                    link=link,
                    description=description,
                    pub_date=pub_date,
                    guid=guid,
                    content=content
                ))
            
            # Update cache
            article_cache = articles
            last_fetch_time = current_time
            
            print(f"Successfully parsed feed, found {len(articles)} articles")
            return articles
        except Exception as e:
            if article_cache:
                return article_cache
            raise Exception(f"Error fetching RSS feed: {e}")

async def extract_player_info(articles: List[Article]):
    """Extract player information from articles."""
    global player_stats_cache
    
    # Check if cache is fresh
    current_time = datetime.datetime.now()
    if last_fetch_time and (current_time - last_fetch_time) < CACHE_DURATION and player_stats_cache:
        return player_stats_cache
    
    # Spurs players to look for with full names
    spurs_players = [
        "Victor Wembanyama", "Wemby", "Devin Vassell", "Jeremy Sochan", 
        "Keldon Johnson", "Tre Jones", "Julian Champagnie", "Zach Collins",
        "Malaki Branham", "Blake Wesley", "Sandro Mamukelashvili", "Dominick Barlow",
        "Charles Bassey", "Harrison Barnes", "Stephon Castle", "Chris Paul", "CP3"
    ]
    
    # Create a mapping of last names to full names
    last_name_mapping = {}
    for player in spurs_players:
        if player in ["Wemby", "CP3"]:  # Skip nicknames
            continue
        
        # Split the name and use last name as key
        name_parts = player.split()
        if len(name_parts) >= 2:  # Make sure we have at least first and last name
            last_name = name_parts[-1]
            last_name_mapping[last_name.lower()] = player
    
    # Add special mappings for nicknames
    nickname_mapping = {
        "wemby": "Victor Wembanyama",
        "cp3": "Chris Paul"
    }
    
    # Combine all name variations into a single search dictionary
    name_variations = {**last_name_mapping, **nickname_mapping}
    
    # Use a dictionary for intermediate processing
    player_mentions_dict = {}
    
    # Extract mentions of players in articles
    for article in articles:
        content = article.content if article.content else article.description
        if not content:
            continue
            
        # Create a plain text version for easier searching
        soup = BeautifulSoup(content, 'html.parser')
        plain_text = soup.get_text()
        
        # First check for full names
        for player in spurs_players:
            if player not in ["Wemby", "CP3"]:  # Skip nicknames here, we'll handle them separately
                if re.search(rf'\b{re.escape(player)}\b', plain_text, re.IGNORECASE):
                    process_player_mention(player, plain_text, article, player_mentions_dict)
        
        # Then check for last names and nicknames
        processed_names = set()  # Track which names we've already processed
        for variation, full_name in name_variations.items():
            # Skip if we've already found this player via their full name
            if full_name in processed_names:
                continue
                
            # Check for this variation
            if re.search(rf'\b{re.escape(variation)}\b', plain_text, re.IGNORECASE):
                process_player_mention(full_name, plain_text, article, player_mentions_dict, search_term=variation)
                processed_names.add(full_name)
    
    # Convert dictionary to PlayerInfo objects
    player_info_objects = {}
    for player_name, data in player_mentions_dict.items():
        # Initialize with empty stats if none exist
        stats = data.get("stats", {})
        player_info_objects[player_name] = PlayerInfo(
            name=player_name,
            stats=stats,
            mentions=data["mentions"]
        )
    
    # Update cache
    player_stats_cache = player_info_objects
    
    return player_info_objects

def process_player_mention(player, plain_text, article, player_mentions_dict, search_term=None):
    """Helper function to process player mentions in text.
    
    Args:
        player: The full/normalized player name
        plain_text: The article text to search
        article: The article object
        player_mentions_dict: Dictionary to collect mentions before converting to PlayerInfo
        search_term: Optional specific term to search for (e.g., nickname or last name)
    """
    # Find sentences containing the player reference
    sentences = re.split(r'(?<=[.!?])\s+', plain_text)
    player_mentions = []
    
    # Determine what term to search for in the sentences
    if search_term:
        term_to_search = search_term
    else:
        term_to_search = player
    
    for sentence in sentences:
        if re.search(rf'\b{re.escape(term_to_search)}\b', sentence, re.IGNORECASE):
            player_mentions.append({
                "text": sentence.strip(),
                "article_title": article.title,
                "article_link": article.link
            })
    
    # Add or update player information in the dictionary
    if player not in player_mentions_dict:
        player_mentions_dict[player] = {"mentions": player_mentions, "stats": {}}
    else:
        player_mentions_dict[player]["mentions"].extend(player_mentions)

async def extract_game_results(articles: List[Article]):
    """Extract game results from articles."""
    global game_results_cache
    
    # NBA teams list for better team name matching
    nba_teams = [
        "76ers",
        "Bucks",
        "Bulls",
        "Cavaliers",
        "Celtics",
        "Clippers",
        "Grizzlies",
        "Hawks",
        "Heat",
        "Hornets",
        "Jazz",
        "Kings",
        "Knicks",
        "Lakers",
        "Magic",
        "Mavericks",
        "Nets",
        "Nuggets",
        "Pacers",
        "Pelicans",
        "Pistons",
        "Raptors",
        "Rockets",
        "Spurs",
        "Suns",
        "Thunder",
        "Timberwolves",
        "Trail Blazers",
        "Warriors",
        "Wizards"
    ]
    
    # Team cities mapping to help with city/team name resolution
    team_cities = {
        "Philadelphia": "76ers",
        "Milwaukee": "Bucks",
        "Chicago": "Bulls",
        "Cleveland": "Cavaliers",
        "Boston": "Celtics",
        "Los Angeles": ["Clippers", "Lakers"],  # Multiple teams in LA
        "Memphis": "Grizzlies",
        "Atlanta": "Hawks",
        "Miami": "Heat",
        "Charlotte": "Hornets",
        "Utah": "Jazz",
        "Sacramento": "Kings",
        "New York": "Knicks",
        "Orlando": "Magic",
        "Dallas": "Mavericks",
        "Brooklyn": "Nets",
        "Denver": "Nuggets",
        "Indiana": "Pacers",
        "New Orleans": "Pelicans",
        "Detroit": "Pistons",
        "Toronto": "Raptors",
        "Houston": "Rockets",
        "San Antonio": "Spurs",
        "Phoenix": "Suns",
        "Oklahoma City": "Thunder",
        "Minnesota": "Timberwolves",
        "Portland": "Trail Blazers",
        "Golden State": "Warriors",
        "Washington": "Wizards"
    }
    
    # Check if cache is fresh
    current_time = datetime.datetime.now()
    if last_fetch_time and (current_time - last_fetch_time) < CACHE_DURATION and game_results_cache:
        return game_results_cache
    
    game_results = []
    
    # Look for game recap articles - expanded keywords list
    game_recap_keywords = ["recap", "final score", "defeat", "win", "lose", "loss", "fall", "beat", 
                           "game thread", "vs", "versus", "against", "victory", "down", "outlast"]
    
    for article in articles:
        # Check if this is likely a game recap
        is_recap = any(keyword in article.title.lower() for keyword in game_recap_keywords)
        
        if is_recap:
            # Initialize game information
            opponent = None
            score = None
            result = None
            location = None
            spurs_score = None
            opponent_score = None
            
            content = article.content if article.content else article.description
            title = article.title
            
            if content:
                soup = BeautifulSoup(content, 'html.parser')
                text = soup.get_text() + " " + title  # Combine content and title for better matching
                
                # Pattern 1: Direct score mentions - "Spurs 120, Lakers 110" or "Lakers 110, Spurs 120"
                pattern1 = r'(?:Spurs|San Antonio)\s+(\d+)[,\s]+(\w+(?:\s+\w+)?)\s+(\d+)|(\w+(?:\s+\w+)?)\s+(\d+)[,\s]+(?:Spurs|San Antonio)\s+(\d+)'
                
                # Pattern 2: Final score mentions - "Final Score: Clippers 122-117 Spurs" or similar
                pattern2 = r'[Ff]inal\s+[Ss]core:?\s+(?:(\w+(?:\s+\w+)?)\s+(\d+)[-–]\s*(\d+)\s+(?:Spurs|San Antonio)|(?:Spurs|San Antonio)\s+(\d+)[-–]\s*(\d+)\s+(\w+(?:\s+\w+)?))'
                
                # Pattern 3: Win/loss statements - "Clippers to a 122-117 win over the Spurs"
                pattern3 = r'(\w+(?:\s+\w+)?)\s+to\s+a\s+(\d+)[-–]\s*(\d+)\s+win\s+(?:\w+\s+){0,2}(?:over|against)\s+(?:the\s+)?(?:Spurs|San Antonio)'
                
                # Pattern 4: Score in title with team names - "Spurs vs. Clippers: 117-122"
                pattern4 = r'(?:Spurs|San Antonio)\s+(?:vs\.?|versus|@|at)\s+(\w+(?:\s+\w+)?)[^0-9]*(\d+)[-–]\s*(\d+)|(\w+(?:\s+\w+)?)\s+(?:vs\.?|versus|@|at)\s+(?:Spurs|San Antonio)[^0-9]*(\d+)[-–]\s*(\d+)'
                
                # Try all patterns
                matched = False
                for pattern_num, pattern in enumerate([pattern1, pattern2, pattern3, pattern4], 1):
                    score_match = re.search(pattern, text, re.IGNORECASE)
                    if score_match:
                        groups = score_match.groups()
                        if pattern_num == 1:  # Direct score format
                            if groups[0]:  # Format: "Spurs 120, Lakers 110"
                                spurs_score = int(groups[0])
                                opponent_raw = groups[1].strip()
                                opponent_score = int(groups[2])
                            else:  # Format: "Lakers 110, Spurs 120"
                                opponent_raw = groups[3].strip()
                                opponent_score = int(groups[4])
                                spurs_score = int(groups[5])
                            
                            # Normalize opponent name using NBA teams list
                            opponent = normalize_team_name(opponent_raw, nba_teams, team_cities)
                        
                        elif pattern_num == 2:  # Final score format
                            if groups[0]:  # Format: "Final Score: Clippers 122-117 Spurs"
                                opponent_raw = groups[0].strip()
                                opponent_score = int(groups[1])
                                spurs_score = int(groups[2])
                            else:  # Format: "Final Score: Spurs 117-122 Clippers"
                                spurs_score = int(groups[3])
                                opponent_score = int(groups[4])
                                opponent_raw = groups[5].strip()
                            
                            # Normalize opponent name
                            opponent = normalize_team_name(opponent_raw, nba_teams, team_cities)
                        
                        elif pattern_num == 3:  # Win statement format
                            # Format: "Clippers to a 122-117 win over the Spurs"
                            opponent_raw = groups[0].strip()
                            opponent_score = int(groups[1])
                            spurs_score = int(groups[2])
                            
                            # Normalize opponent name
                            opponent = normalize_team_name(opponent_raw, nba_teams, team_cities)
                        
                        elif pattern_num == 4:  # Title with score format
                            if groups[0]:  # Format: "Spurs vs. Clippers: 117-122"
                                opponent_raw = groups[0].strip()
                                # Determine which score belongs to which team based on context
                                score1, score2 = int(groups[1]), int(groups[2])
                                if "win" in text.lower() and "spurs win" in text.lower():
                                    spurs_score, opponent_score = max(score1, score2), min(score1, score2)
                                elif "loss" in text.lower() and "spurs loss" in text.lower():
                                    spurs_score, opponent_score = min(score1, score2), max(score1, score2)
                                else:
                                    # If no clear indicator, assume first number is Spurs
                                    spurs_score, opponent_score = score1, score2
                            else:  # Format: "Clippers vs. Spurs: 122-117"
                                opponent_raw = groups[3].strip()
                                # Same logic as above
                                score1, score2 = int(groups[4]), int(groups[5])
                                if "win" in text.lower() and "spurs win" in text.lower():
                                    spurs_score, opponent_score = max(score1, score2), min(score1, score2)
                                elif "loss" in text.lower() and "spurs loss" in text.lower():
                                    spurs_score, opponent_score = min(score1, score2), max(score1, score2)
                                else:
                                    # If no clear indicator, assume second number is Spurs
                                    opponent_score, spurs_score = score1, score2
                            
                            # Normalize opponent name
                            opponent = normalize_team_name(opponent_raw, nba_teams, team_cities)
                        
                        matched = True
                        break
                
                # If we didn't match a score pattern, try to infer result from keywords
                if not matched:
                    # Try to find opponent by scanning for NBA team names in the text
                    for team in nba_teams:
                        if team != "Spurs" and team.lower() in text.lower():
                            opponent = team
                            break
                    
                    # If still no opponent, try to extract from city names
                    if not opponent:
                        for city, team in team_cities.items():
                            if city != "San Antonio" and city.lower() in text.lower():
                                # Handle Los Angeles special case
                                if isinstance(team, list):
                                    # If both LA teams are mentioned, use the one that appears more
                                    if all(t.lower() in text.lower() for t in team):
                                        # Count occurrences to determine which LA team
                                        team_counts = {t: text.lower().count(t.lower()) for t in team}
                                        opponent = max(team_counts.items(), key=lambda x: x[1])[0]
                                    # If only one LA team is mentioned, use that one
                                    elif any(t.lower() in text.lower() for t in team):
                                        for t in team:
                                            if t.lower() in text.lower():
                                                opponent = t
                                                break
                                    # Default to first team if no clear match
                                    else:
                                        opponent = team[0]
                                else:
                                    opponent = team
                                break
                    
                    # Try to extract teams from "vs" format
                    if not opponent:
                        teams_pattern = r'(?:Spurs|San Antonio)\s+(?:vs\.?|versus|against|at|@)\s+(\w+(?:\s+\w+)?)|(\w+(?:\s+\w+)?)\s+(?:vs\.?|versus|against|at|@)\s+(?:Spurs|San Antonio)'
                        teams_match = re.search(teams_pattern, text, re.IGNORECASE)
                        if teams_match:
                            groups = teams_match.groups()
                            opponent_raw = next((g for g in groups if g), None)
                            if opponent_raw:
                                opponent = normalize_team_name(opponent_raw.strip(), nba_teams, team_cities)
                    
                    # Try to infer result from text
                    spurs_win_indicators = ["spurs win", "spurs defeat", "spurs beat", "spurs down", 
                                           "san antonio win", "san antonio defeat", "san antonio beat"]
                    spurs_loss_indicators = ["spurs lose", "spurs fall", "spurs lost", "defeated by", 
                                            "beaten by", "fall to", "lose to", "win over spurs", 
                                            "victory over spurs", "over the spurs"]
                    
                    text_lower = text.lower()
                    if any(indicator in text_lower for indicator in spurs_win_indicators):
                        result = "Win"
                    elif any(indicator in text_lower for indicator in spurs_loss_indicators):
                        result = "Loss"
                
                # If we have scores, set the result based on those
                if spurs_score is not None and opponent_score is not None:
                    score = f"Spurs {spurs_score}, {opponent} {opponent_score}"
                    result = "Win" if spurs_score > opponent_score else "Loss"
                
                # Extract location (home/away)
                location_patterns = [
                    r'(?:played|playing|game)\s+at\s+home', 
                    r'(?:played|playing|game)\s+on\s+the\s+road', 
                    r'in\s+San\s+Antonio', 
                    r'at\s+the\s+(?:AT&T|Frost\s+Bank)\s+Center',
                    r'away\s+game',
                    r'host(?:s|ing|ed)\s+the',
                    r'visit(?:s|ing|ed)\s+the'
                ]
                
                for pattern in location_patterns:
                    location_match = re.search(pattern, text, re.IGNORECASE)
                    if location_match:
                        location_text = location_match.group(0).lower()
                        if any(loc in location_text for loc in ['at home', 'in san antonio', 'at the', 'host']):
                            location = "Home"
                        else:
                            location = "Away"
                        break
                
                # If location still not determined, try to infer from "vs" or "@" format
                if not location and opponent:
                    vs_pattern = r'(?:Spurs|San Antonio)\s+@\s+' + re.escape(opponent)
                    at_pattern = r'' + re.escape(opponent) + r'\s+@\s+(?:Spurs|San Antonio)'
                    
                    if re.search(vs_pattern, text, re.IGNORECASE):
                        location = "Away"
                    elif re.search(at_pattern, text, re.IGNORECASE):
                        location = "Home"
            
            # If we have enough information, add to results
            if result and score:
                game_results.append(GameResult(
                    date=article.pub_date,
                    opponent=opponent if opponent else "Unknown",
                    score=score if score else "Score not found",
                    result=result if result else "Unknown",
                    location=location if location else "Unknown"
                ))
    
    # Update cache
    game_results_cache = game_results
    
    return game_results

def normalize_team_name(raw_name: str, nba_teams: List[str], team_cities: Dict[str, Union[str, List[str]]]) -> str:
    """Normalize a team name by matching it to official NBA team names."""
    if not raw_name:
        return "Unknown"
    
    # Direct match with team name
    for team in nba_teams:
        if team.lower() == raw_name.lower() or team.lower() in raw_name.lower():
            return team
    
    # Match with city name
    for city, team in team_cities.items():
        if city.lower() == raw_name.lower() or city.lower() in raw_name.lower():
            # Handle the Los Angeles special case
            if isinstance(team, list):
                # Default to the first team unless more info
                return team[0]
            return team
    
    # If no match found, return the original
    return raw_name

# Define MCP resources
@mcp.resource("articles://latest")
async def get_latest_articles():
    """Get the latest articles from Pounding The Rock."""
    articles = await fetch_and_parse_rss()
    
    # Format articles for display
    formatted_articles = []
    for article in articles[:10]:  # Limit to 10 most recent
        formatted_articles.append(f"""
Title: {article.title}
Published: {article.pub_date}
Link: {article.link}
Summary: {article.description}
-------------------
        """)
    
    return "\n".join(formatted_articles)

@mcp.resource("articles://{article_id}")
async def get_article_by_id(article_id: str):
    """Get a specific article by its ID."""
    articles = await fetch_and_parse_rss()
    
    # Find the article with matching ID
    for article in articles:
        # Create a simplified ID from the title
        simple_id = re.sub(r'[^a-z0-9]', '-', article.title.lower())
        if simple_id == article_id or article.guid.endswith(article_id):
            return f"""
Title: {article.title}
Published: {article.pub_date}
Link: {article.link}
Content: {article.content if article.content else article.description}
            """
    
    return f"Article with ID {article_id} not found."

@mcp.resource("gameresults://recent")
async def get_recent_game_results():
    """Get recent game results."""
    articles = await fetch_and_parse_rss()
    game_results = await extract_game_results(articles)
    
    if not game_results:
        return "No recent game results found."
    
    # Format game results
    formatted_results = []
    for game in game_results[:5]:  # Limit to 5 most recent
        formatted_results.append(f"""
Date: {game.date}
Matchup: Spurs vs {game.opponent}
Result: {game.result}
Score: {game.score}
Location: {game.location}
-------------------
        """)
    
    return "\n".join(formatted_results)

@mcp.resource("players://list")
async def get_players_list():
    """Get a list of Spurs players mentioned in articles."""
    articles = await fetch_and_parse_rss()
    player_data = await extract_player_info(articles)
    
    player_names = list(player_data.keys())
    return "Spurs players mentioned in recent articles:\n" + "\n".join(player_names)

# Define MCP tools
@mcp.tool()
async def get_player_info(player_name: str) -> str:
    """Get information about a specific Spurs player including stats and recent mentions.
    
    Args:
        player_name: Name of the Spurs player to get information about
    """
    articles = await fetch_and_parse_rss()
    player_data = await extract_player_info(articles)
    
    # Find player (case-insensitive)
    matched_player = None
    for name in player_data:
        if name.lower() == player_name.lower():
            matched_player = name
            break
    
    if not matched_player:
        return f"Player '{player_name}' not found in recent articles. Try another player name."
    
    player_info = player_data[matched_player]
    
    # Format player stats - use attribute access instead of dictionary access
    stats = player_info.stats
    stats_text = "\n".join([f"{key}: {value}" for key, value in stats.items()])
    
    # Format player mentions - use attribute access instead of dictionary access
    mentions = player_info.mentions
    mentions_text = ""
    for i, mention in enumerate(mentions[:5], 1):  # Limit to 5 mentions
        mentions_text += f"\n{i}. \"{mention['text']}\" - {mention['article_title']}"
    
    return f"""
Player: {matched_player}

Stats:
{stats_text}

Recent Mentions:{mentions_text}
    """

@mcp.tool()
async def get_recent_results() -> str:
    """Get recent San Antonio Spurs game results from articles."""
    articles = await fetch_and_parse_rss()

    if not articles:
        return "No blog articles found."

    game_results = await extract_game_results(articles)
    
    if not game_results:
        return "No recent game results found in the blog articles."
    
    # Format results
    results_text = ""
    for i, game in enumerate(game_results, 1):
        results_text += f"""
Game {i}:
Date: {game.date}
Opponent: {game.opponent}
Result: {game.result}
Score: {game.score}
Location: {game.location}
-------------------
        """
    
    return f"Recent Spurs Game Results:\n{results_text}"

@mcp.tool()
async def search_articles(keyword: str) -> str:
    """Search for articles containing a specific keyword.
    
    Args:
        keyword: The keyword to search for in article titles and content
    """
    articles = await fetch_and_parse_rss()
    
    # Split multi-word keywords for better matching
    keywords = keyword.lower().split()
    
    matching_articles = []
    highlighted_snippets = {}
    
    for article in articles:
        title = article.title or ""
        content_raw = article.content if article.content else article.description or ""
        
        # Parse HTML content to get plain text
        if content_raw:
            soup = BeautifulSoup(content_raw, 'html.parser')
            content = soup.get_text()
        else:
            content = ""
        
        combined_text = (title + " " + content).lower()
        
        # Check if all words in the keyword phrase are in the article
        if len(keywords) > 1:
            # For multi-word phrases, try exact matching first
            if keyword.lower() in combined_text:
                matching_articles.append(article)
                
                # Extract a snippet containing the keyword for context
                keyword_index = combined_text.find(keyword.lower())
                start = max(0, keyword_index - 100)
                end = min(len(combined_text), keyword_index + len(keyword) + 100)
                snippet = combined_text[start:end]
                
                # Add ellipses if we're not at the beginning or end
                if start > 0:
                    snippet = "..." + snippet
                if end < len(combined_text):
                    snippet = snippet + "..."
                
                highlighted_snippets[article.guid] = snippet.replace(
                    keyword.lower(), 
                    f"**{keyword.lower()}**"
                )
            
            # If exact match fails, check if all words are present
            elif all(word in combined_text for word in keywords):
                matching_articles.append(article)
                highlighted_snippets[article.guid] = "Multiple keyword matches found in article"
        else:
            # For single-word keywords, use word boundary search
            pattern = rf'\b{re.escape(keyword)}\b'
            if re.search(pattern, combined_text, re.IGNORECASE):
                matching_articles.append(article)
                
                # Find all matches to extract the best snippet
                matches = list(re.finditer(pattern, combined_text, re.IGNORECASE))
                if matches:
                    # Use the first match for the snippet
                    match = matches[0]
                    start = max(0, match.start() - 100)
                    end = min(len(combined_text), match.end() + 100)
                    snippet = combined_text[start:end]
                    
                    # Add ellipses if needed
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(combined_text):
                        snippet = snippet + "..."
                    
                    # Bold the keyword in the snippet
                    pattern_with_case = re.compile(pattern, re.IGNORECASE)
                    highlighted_snippets[article.guid] = pattern_with_case.sub(
                        lambda m: f"**{m.group(0)}**", 
                        snippet
                    )
                else:
                    # Fallback if regex match worked but finditer failed
                    highlighted_snippets[article.guid] = "Keyword found in article"
    
    if not matching_articles:
        return f"No articles found containing the keyword '{keyword}'."
    
    # Sort articles by relevance (title matches first, then content matches)
    def relevance_score(article):
        # Articles with the keyword in the title get higher priority
        title_match = keyword.lower() in article.title.lower()
        # Count occurrences for secondary sorting
        count = (article.title + (article.content or article.description or "")).lower().count(keyword.lower())
        return (title_match, count)
    
    matching_articles.sort(key=relevance_score, reverse=True)
    
    # Format matching articles with snippets
    results = []
    for article in matching_articles:
        snippet = highlighted_snippets.get(article.guid, "")
        results.append(f"""
Title: {article.title}
Published: {article.pub_date}
Link: {article.link}
Snippet: {snippet}
-------------------
        """)
    
    return f"Found {len(matching_articles)} articles containing '{keyword}':\n" + "\n".join(results)

@mcp.prompt()
def generate_player_comparison(player1: str, player2: str) -> str:
    """Create a prompt to compare two Spurs players."""
    return f"""
Please compare the following San Antonio Spurs players based on their recent performances, stats, and mentions in articles:

Player 1: {player1}
Player 2: {player2}

Consider their:
- Statistical production
- Impact on winning
- Role on the team
- Recent trends in performance
- Media and fan perceptions
    """

@mcp.prompt()
def generate_team_news_request(days: int = 7) -> str:
    """Create a prompt to request recent Spurs news."""
    return f"""
Please provide a summary of the most important San Antonio Spurs news and developments from the past {days} days. Include:

- Game results and highlights
- Player performances
- Injury updates
- Team trends
- Front office moves
- Upcoming schedule
    """

@mcp.prompt()
def generate_nba_news_request() -> str:
    """Create a prompt to request related NBA news from the official NBA website."""
    return """
Please use the NBA official website to find the latest news related to:

1. San Antonio Spurs standings in the Western Conference
2. Upcoming games on the Spurs schedule
3. Any league-wide news that affects the Spurs
4. Updates on Victor Wembanyama's rookie season and awards race
5. Trade rumors or roster changes involving the Spurs
    """

# Run the server
if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')