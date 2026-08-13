"""Public Reddit JSON research for the paper-trading reddit lane.

Fetches finance subreddit listings (no login). Does not scrape private content.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
import sqlite3

from app.config import settings
from app.freshness_service import touch_data_source
from app.news_service import ingest_news_events
from app.schemas import NewsEventIn, RedditMentionOut, RedditPostOut, RedditResearchOut

REDDIT_SOURCE = "reddit"
DEFAULT_LIMIT = 25
MAX_LIMIT = 50
MAX_INGEST_EVENTS = 80
REDDIT_JSON_URL = "https://www.reddit.com/r/{subreddit}/hot.json"

CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")
TICKER_STOPWORDS = {
    "A", "I", "AI", "CEO", "CFO", "CPI", "DD", "EPS", "ETF", "EV", "FDA", "FOMC",
    "GDP", "IMO", "IPO", "PE", "SEC", "USA", "USD", "WSB", "YOLO", "ATH", "ATM",
    "OTM", "ITM", "EOD", "EOW", "ATH", "CEO", "THE", "AND", "FOR", "YOU", "ARE",
    "NOT", "THIS", "THAT", "WITH", "FROM", "JUST", "HAVE", "WILL", "BEEN",
}

BULLISH_WORDS = ("moon", "calls", "breakout", "squeeze", "rip", "bull", "long")
BEARISH_WORDS = ("crash", "dump", "puts", "baghold", "sold", "bear", "short")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_subreddits(value: str | None) -> list[str]:
    raw = value if value is not None else settings.reddit_subreddits
    seen: set[str] = set()
    out: list[str] = []
    for part in raw.split(","):
        name = re.sub(r"[^A-Za-z0-9_]", "", part.strip())
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out or ["wallstreetbets", "stocks", "investing"]


def extract_tickers(text: str, allowed: set[str] | None = None) -> list[str]:
    found: set[str] = set()
    haystack = text or ""
    for match in CASHTAG_RE.finditer(haystack.upper()):
        found.add(match.group(1))
    if allowed:
        upper_text = haystack.upper()
        for symbol in allowed:
            if re.search(rf"(?<![A-Z]){re.escape(symbol)}(?![A-Z])", upper_text):
                found.add(symbol)
    cleaned = []
    for symbol in sorted(found):
        if symbol in TICKER_STOPWORDS or len(symbol) > 5:
            continue
        cleaned.append(symbol)
    return cleaned


def post_sentiment(upvote_ratio: float | None, title: str) -> float:
    base = 0.0
    if upvote_ratio is not None:
        base = (float(upvote_ratio) - 0.5) * 2.0
    lowered = (title or "").lower()
    if any(word in lowered for word in BEARISH_WORDS):
        base -= 0.2
    if any(word in lowered for word in BULLISH_WORDS):
        base += 0.15
    return max(-1.0, min(1.0, base))


def post_importance(score: int, comments: int) -> float:
    score_part = min(1.0, max(0, score) / 4000.0) * 0.6
    comment_part = min(1.0, max(0, comments) / 2000.0) * 0.4
    return round(min(1.0, score_part + comment_part), 4)


def _created_at_iso(created_utc: float | int | None) -> str:
    if not created_utc:
        return _iso_now()
    return datetime.fromtimestamp(float(created_utc), tz=timezone.utc).isoformat()


def _child_to_post(child: dict, allowed: set[str] | None) -> RedditPostOut | None:
    data = child.get("data") if isinstance(child, dict) else None
    if not isinstance(data, dict):
        return None
    post_id = str(data.get("id") or "").strip()
    title = str(data.get("title") or "").strip()
    if not post_id or not title:
        return None
    selftext = str(data.get("selftext") or "")
    tickers = extract_tickers(f"{title}\n{selftext}", allowed)
    permalink = str(data.get("permalink") or "")
    if permalink and not permalink.startswith("http"):
        permalink = urljoin("https://www.reddit.com", permalink)
    upvote = data.get("upvote_ratio")
    try:
        upvote_ratio = float(upvote) if upvote is not None else None
    except (TypeError, ValueError):
        upvote_ratio = None
    score = int(data.get("score") or 0)
    comments = int(data.get("num_comments") or 0)
    return RedditPostOut(
        id=post_id,
        subreddit=str(data.get("subreddit") or ""),
        title=title,
        score=score,
        comments=comments,
        upvote_ratio=upvote_ratio,
        created_at=_created_at_iso(data.get("created_utc")),
        permalink=permalink,
        tickers=tickers,
        sentiment=round(post_sentiment(upvote_ratio, title), 4),
        importance=post_importance(score, comments),
    )


def _mentions_from_posts(posts: list[RedditPostOut]) -> list[RedditMentionOut]:
    grouped: dict[str, list[RedditPostOut]] = defaultdict(list)
    for post in posts:
        for ticker in post.tickers:
            grouped[ticker].append(post)
    mentions: list[RedditMentionOut] = []
    for symbol, group in grouped.items():
        titles = [item.title for item in sorted(group, key=lambda p: p.score, reverse=True)[:3]]
        avg = sum(item.sentiment for item in group) / len(group)
        mentions.append(
            RedditMentionOut(
                symbol=symbol,
                post_count=len(group),
                avg_sentiment=round(avg, 4),
                max_importance=max(item.importance for item in group),
                sample_titles=titles,
            )
        )
    mentions.sort(key=lambda row: (row.post_count, row.max_importance), reverse=True)
    return mentions


def _fetch_subreddit(
    client: httpx.Client,
    subreddit: str,
    limit: int,
    allowed: set[str] | None,
) -> tuple[list[RedditPostOut], str | None]:
    url = REDDIT_JSON_URL.format(subreddit=subreddit)
    try:
        response = client.get(url, params={"limit": limit, "raw_json": 1}, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return [], f"{subreddit}: {exc}"
    children = ((payload.get("data") or {}).get("children")) if isinstance(payload, dict) else None
    if not isinstance(children, list):
        return [], f"{subreddit}: unexpected JSON shape"
    posts: list[RedditPostOut] = []
    for child in children:
        post = _child_to_post(child, allowed)
        if post is not None:
            posts.append(post)
    return posts, None


def fetch_reddit_research(
    *,
    subreddits: str | None = None,
    limit: int = DEFAULT_LIMIT,
    allowed_symbols: list[str] | None = None,
) -> RedditResearchOut:
    names = _parse_subreddits(subreddits)
    capped = max(1, min(limit, MAX_LIMIT))
    allowed = {s.upper() for s in allowed_symbols} if allowed_symbols else None
    headers = {"User-Agent": settings.reddit_user_agent}
    posts: list[RedditPostOut] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        for name in names:
            batch, error = _fetch_subreddit(client, name, capped, allowed)
            if error:
                errors.append(error)
                continue
            for post in batch:
                if post.id in seen_ids:
                    continue
                seen_ids.add(post.id)
                posts.append(post)
    posts.sort(key=lambda item: item.score, reverse=True)
    return RedditResearchOut(
        fetched_at=_iso_now(),
        subreddits=names,
        posts=posts,
        mentions=_mentions_from_posts(posts),
        errors=errors,
    )


def _events_from_research(research: RedditResearchOut) -> list[NewsEventIn]:
    events: list[NewsEventIn] = []
    for post in research.posts:
        tickers = post.tickers or [None]
        for ticker in tickers[:3]:
            if len(events) >= MAX_INGEST_EVENTS:
                return events
            summary_parts = [
                f"r/{post.subreddit}: {post.title}",
                f"score={post.score} comments={post.comments}",
            ]
            if post.permalink:
                summary_parts.append(post.permalink)
            events.append(
                NewsEventIn(
                    symbol=ticker,
                    source=REDDIT_SOURCE,
                    event_at=post.created_at,
                    event_type="reddit_post",
                    importance=post.importance,
                    sentiment=post.sentiment,
                    summary=" | ".join(summary_parts),
                    external_id=f"reddit:{post.id}:{ticker or 'market'}",
                )
            )
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for mention in research.mentions:
        if len(events) >= MAX_INGEST_EVENTS:
            break
        titles = "; ".join(mention.sample_titles[:2])
        events.append(
            NewsEventIn(
                symbol=mention.symbol,
                source=REDDIT_SOURCE,
                event_at=research.fetched_at,
                event_type="reddit_mention",
                importance=mention.max_importance,
                sentiment=mention.avg_sentiment,
                summary=(
                    f"{mention.symbol}: {mention.post_count} Reddit posts, "
                    f"avg sentiment {mention.avg_sentiment:.2f}. {titles}"
                ),
                external_id=f"reddit-mention:{today}:{mention.symbol}",
            )
        )
    return events


def ingest_reddit_research(
    conn: sqlite3.Connection,
    research: RedditResearchOut,
) -> tuple[int, int]:
    events = _events_from_research(research)
    if not events:
        touch_data_source(conn, "reddit", detail="0 reddit events")
        return 0, 0
    inserted, skipped = ingest_news_events(conn, events)
    touch_data_source(
        conn,
        "reddit",
        detail=f"{inserted} reddit event(s) ingested",
    )
    return inserted, skipped
