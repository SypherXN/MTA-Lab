import unittest
from unittest.mock import MagicMock, patch

from app.reddit_service import extract_tickers, fetch_reddit_research, post_sentiment


def _listing(posts: list[dict]) -> dict:
    children = []
    for index, post in enumerate(posts, 1):
        children.append(
            {
                "data": {
                    "id": post.get("id", f"id{index}"),
                    "title": post["title"],
                    "selftext": post.get("selftext", ""),
                    "score": post.get("score", 100),
                    "upvote_ratio": post.get("upvote_ratio", 0.8),
                    "num_comments": post.get("num_comments", 10),
                    "created_utc": post.get("created_utc", 1700000000),
                    "permalink": post.get("permalink", f"/r/stocks/comments/id{index}/x/"),
                    "subreddit": post.get("subreddit", "stocks"),
                }
            }
        )
    return {"data": {"children": children}}


class TickerExtractionTests(unittest.TestCase):
    def test_cashtag_and_allowed_symbol(self):
        text = "$NVDA ripping while AAPL holds up. CEO says GDP is fine."
        tickers = extract_tickers(text, allowed={"NVDA", "AAPL", "SPY"})
        self.assertEqual(tickers, ["AAPL", "NVDA"])

    def test_stopwords_dropped(self):
        tickers = extract_tickers("The CEO and the ETF IPO", allowed={"CEO", "ETF", "IPO"})
        self.assertEqual(tickers, [])

    def test_sentiment_bounds(self):
        self.assertGreater(post_sentiment(0.9, "moon breakout"), 0)
        self.assertLess(post_sentiment(0.2, "crash dump"), 0)


class RedditFetchTests(unittest.TestCase):
    def test_fetch_mentions(self):
        payload = _listing(
            [
                {"title": "$NVDA earnings crush", "score": 4000, "upvote_ratio": 0.94},
                {"title": "SPY dip buyers", "score": 800, "upvote_ratio": 0.7},
            ]
        )
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = payload
        fake = MagicMock()
        fake.get.return_value = response
        with patch("app.reddit_service.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value = fake
            research = fetch_reddit_research(
                subreddits="stocks",
                limit=10,
                allowed_symbols=["NVDA", "SPY", "QQQ"],
            )
        self.assertGreaterEqual(len(research.posts), 1)
        symbols = {row.symbol for row in research.mentions}
        self.assertIn("NVDA", symbols)
        self.assertIn("SPY", symbols)


if __name__ == "__main__":
    unittest.main()
