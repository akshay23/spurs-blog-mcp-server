#!/usr/bin/env python3
from mcp.server.fastmcp import FastMCP, Context, Image
import httpx
import xml.etree.ElementTree as ET
import re
import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import asyncio
from bs4 import BeautifulSoup
import json

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
            namespace = {'atom': 'http://www.w3.org/2005/Atom'}
            articles = []
            
            # Process Atom feed (entries instead of items)
            for entry in root.findall('.//atom:entry', namespace) or root.findall('.//entry'):
                # Get title
                title_elem = entry.find('.//atom:title', namespace) or entry.find('title')
                title = title_elem.text if title_elem is not None else "No Title"
                
                # Get link (may be in different formats in Atom)
                link = None
                link_elem = entry.find('.//atom:link[@rel="alternate"][@type="text/html"]', namespace) or entry.find('link[@rel="alternate"]')
                if link_elem is not None:
                    link = link_elem.get('href')
                
                # Get description/content
                content_elem = entry.find('.//atom:content', namespace) or entry.find('content')
                description = content_elem.text if content_elem is not None and content_elem.text else ""
                
                # If content has HTML type, use the content directly
                if content_elem is not None and content_elem.get('type') == 'html':
                    content = content_elem.text
                else:
                    content = description
                
                # Get publication date
                pub_date_elem = entry.find('.//atom:published', namespace) or entry.find('published') or entry.find('.//atom:updated', namespace) or entry.find('updated')
                pub_date = pub_date_elem.text if pub_date_elem is not None else ""
                
                # Get ID
                id_elem = entry.find('.//atom:id', namespace) or entry.find('id')
                guid = id_elem.text if id_elem is not None else link
                
                article = Article(
                    title=title,
                    link=link,
                    description=description,
                    pub_date=pub_date,
                    guid=guid,
                    content=content
                )
                articles.append(article)
            
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
    
    # Spurs players to look for
    spurs_players = [
        "Victor Wembanyama", "Wemby", "Devin Vassell", "Jeremy Sochan", 
        "Keldon Johnson", "Tre Jones", "Julian Champagnie", "Zach Collins",
        "Malaki Branham", "Blake Wesley", "Sandro Mamukelashvili", "Dominick Barlow",
        "Charles Bassey", "Harrison Barnes", "Stephon Castle", "Chris Paul", "CP3"
    ]
    
    player_data = {}
    
    # Extract mentions of players in articles
    for article in articles:
        content = article.content if article.content else article.description
        if not content:
            continue
            
        # Create a plain text version for easier searching
        soup = BeautifulSoup(content, 'html.parser')
        plain_text = soup.get_text()
        
        for player in spurs_players:
            # Look for mentions of the player (case insensitive)
            if re.search(rf'\b{re.escape(player)}\b', plain_text, re.IGNORECASE):
                # Find sentences containing the player name
                sentences = re.split(r'(?<=[.!?])\s+', plain_text)
                player_mentions = []
                
                for sentence in sentences:
                    if re.search(rf'\b{re.escape(player)}\b', sentence, re.IGNORECASE):
                        player_mentions.append({
                            "text": sentence.strip(),
                            "article_title": article.title,
                            "article_link": article.link
                        })
                
                # Normalize player names (e.g., "Wemby" -> "Victor Wembanyama")
                normalized_name = player
                if player == "Wemby":
                    normalized_name = "Victor Wembanyama"
                elif player == "CP3":
                    normalized_name = "Chris Paul"
                
                # Add or update player information
                if normalized_name not in player_data:
                    return f"Player '{normalized_name}' not found in recent articles. Try another player name."
                else:
                    player_data[normalized_name]["mentions"].extend(player_mentions)
    
    # Update cache
    player_stats_cache = player_data
    
    return player_data

async def extract_game_results(articles: List[Article]):
    """Extract game results from articles."""
    global game_results_cache
    
    # Check if cache is fresh
    current_time = datetime.datetime.now()
    if last_fetch_time and (current_time - last_fetch_time) < CACHE_DURATION and game_results_cache:
        return game_results_cache
    
    game_results = []
    
    # Look for game recap articles
    game_recap_keywords = ["recap", "final score", "defeat", "win", "lose", "fall to", "game thread"]
    
    for article in articles:
        # Check if this is likely a game recap
        is_recap = any(keyword in article.title.lower() for keyword in game_recap_keywords)
        
        if is_recap:
            # Try to extract game information
            opponent = None
            score = None
            result = None
            location = None
            
            # Use regex to find scores like "Spurs 120, Lakers 110" or "Lakers 110, Spurs 120"
            score_pattern = r'(?:Spurs|San Antonio)\s+(\d+)[,\s]+(\w+)\s+(\d+)|(\w+)\s+(\d+)[,\s]+(?:Spurs|San Antonio)\s+(\d+)'
            content = article.content if article.content else article.description
            if content:
                soup = BeautifulSoup(content, 'html.parser')
                text = soup.get_text()
                
                # Try to extract opponent and score
                score_match = re.search(score_pattern, text)
                if score_match:
                    groups = score_match.groups()
                    if groups[0]:  # Format: "Spurs 120, Lakers 110"
                        spurs_score = int(groups[0])
                        opponent = groups[1]
                        opponent_score = int(groups[2])
                    else:  # Format: "Lakers 110, Spurs 120"
                        opponent = groups[3]
                        opponent_score = int(groups[4])
                        spurs_score = int(groups[5])
                    
                    score = f"Spurs {spurs_score}, {opponent} {opponent_score}"
                    result = "Win" if spurs_score > opponent_score else "Loss"
                else:
                    # Try to infer from title
                    title_parts = article.title.split()
                    for i, part in enumerate(title_parts):
                        if part.lower() in ["defeat", "beat", "over", "down"]:
                            if "spurs" in article.title.lower():
                                if i > 0 and "spurs" in title_parts[i-1].lower():
                                    result = "Win"
                                else:
                                    result = "Loss"
                            break
                        elif part.lower() in ["fall", "lose", "lost"]:
                            result = "Loss"
                            break
                
                # Try to extract location (home/away)
                location_patterns = [r'at home', r'on the road', r'in San Antonio', r'away']
                for pattern in location_patterns:
                    location_match = re.search(pattern, text, re.IGNORECASE)
                    if location_match:
                        location_text = location_match.group(0).lower()
                        if any(loc in location_text for loc in ['at home', 'in san antonio']):
                            location = "Home"
                        else:
                            location = "Away"
                        break
            
            # If we have enough information, add to results
            if result or score or opponent:
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
    
    # Format player stats
    stats = player_info["stats"]
    stats_text = "\n".join([f"{key}: {value}" for key, value in stats.items()])
    
    # Format player mentions
    mentions = player_info["mentions"]
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
    
    matching_articles = []
    for article in articles:
        content = article.content if article.content else article.description
        if re.search(rf'\b{re.escape(keyword)}\b', article.title + content, re.IGNORECASE):
            matching_articles.append(article)
    
    if not matching_articles:
        return f"No articles found containing the keyword '{keyword}'."
    
    # Format matching articles
    results = []
    for article in matching_articles:
        results.append(f"""
Title: {article.title}
Published: {article.pub_date}
Link: {article.link}
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