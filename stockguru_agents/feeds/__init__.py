"""
StockGuru Data Feed Connectors
Auto-selects the best available feed based on configured .env keys.
"""
from .feed_manager import FeedManager

# Singleton — import this everywhere
feed_manager = FeedManager()
