"""
Autopost service — Degen trading persona

- Text-only LLM usage (OpenRouter-safe)
- Guaranteed fallback
- Hard clamp at 250 chars
"""

import logging
import time
import random
from typing import Any, List, Optional

from services.database import Database
from services.llm import LLMClient
from tweepy import Client, TweepyException

logger = logging.getLogger(__name__)

MAX_CHARS = 250

# =========================
# FALLBACK TWEETS (≤250 chars)
# =========================
FALLBACK_TWEETS = [
    "spent hours mapping levels, scenarios, and invalidations. entered anyway with no stop because it felt right. price immediately showed me why feelings are not a strategy.",
    "every trade starts with confidence, slowly turns into hope, then ends with acceptance. somehow i still act surprised when the cycle repeats exactly the same way.",
    "watched price respect my levels perfectly while i hesitated. entered late, sized too big, and blamed execution instead of the obvious lack of discipline.",
    "told myself i was waiting for confirmation. what i really did was wait until the risk was worse and the reward was gone.",
    "another trade where i was right about direction, wrong about timing, and absolutely confident it would still work out anyway.",
    "i don’t chase tops or bottoms. i chase the feeling that this time i finally figured it out.",
    "the plan was simple. the execution wasn’t. the result was predictable.",
]

# =========================
# SYSTEM PROMPT
# =========================
SYSTEM_PROMPT = """
You are a degen trading Twitter account.

Style rules:
- First-person
- Casual, cynical trader tone
- Aim for 180–250 characters
- Never exceed 250 characters
- No emojis
- No hashtags
- No advice
- No explanations
- No meta commentary

Content:
- Bad entries and exits
- Overconfidence, regret, cope
- Charts, candles, leverage, timing
- Emotional, observational, impulsive

Write tweets that feel posted right after staring at charts too long.
"""

# =========================
# Helper: normalize post text
# =========================
def normalize_post_text(result: Any) -> str:
    """
    Ensures post_text is always a string.
    Handles dict, string, or broken LLM output.
    """
    if isinstance(result, str) and result.strip():
        return result.strip()

    if isinstance(result, dict):
        for key in ("post", "text", "content", "tweet"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    # fallback if nothing usable
    return random.choice(FALLBACK_TWEETS)

# =========================
# Twitter client
# =========================
class TwitterClient:
    def __init__(self):
        # Replace with your credentials
        self.client = Client(
            bearer_token="YOUR_BEARER_TOKEN",
            consumer_key="YOUR_CONSUMER_KEY",
            consumer_secret="YOUR_CONSUMER_SECRET",
            access_token="YOUR_ACCESS_TOKEN",
            access_token_secret="YOUR_ACCESS_SECRET",
            wait_on_rate_limit=True,
        )

    async def post(self, text: Optional[str] = None, media_ids: Optional[List[str]] = None) -> dict:
        """
        Safely posts a tweet.
        Raises ValueError if both text and media are empty.
        Returns Twitter API response dict.
        """
        text = (text or "").strip()
        media_ids = media_ids or []

        if not text and not media_ids:
            logger.error("Attempted to post empty tweet: text and media are both empty")
            raise ValueError("Cannot post empty tweet: must provide text or media")

        try:
            response = self.client.create_tweet(
                text=text if text else None,
                media_ids=media_ids if media_ids else None,
            )
            logger.info(f"[TWITTER] Tweet posted successfully: {response.data.get('id')}")
            return response.data or {}
        except TweepyException as e:
            logger.error(f"[TWITTER] Failed to post tweet: {e}")
            raise

# =========================
# AutoPost Service
# =========================
class AutoPostService:
    def __init__(self, db: Database, tier_manager=None):
        self.db = db
        self.llm = LLMClient()
        self.twitter = TwitterClient()
        self.tier_manager = tier_manager

    async def safe_chat(self, messages: list[dict]) -> Any:
        """LLM call that never crashes autopost."""
        try:
            return await self.llm.chat(messages)
        except Exception as e:
            logger.error(f"[LLM] Failed: {e}")
            return None

    async def run(self) -> dict[str, Any]:
        start_time = time.time()
        logger.info("[AUTOPOST] === Starting ===")

        try:
            # -------------------------
            # Tier check
            # -------------------------
            if self.tier_manager:
                can_post, reason = self.tier_manager.can_post()
                if not can_post:
                    logger.warning(f"[AUTOPOST] Blocked: {reason}")
                    return {
                        "success": False,
                        "error": f"posting_blocked: {reason}",
                        "tier": self.tier_manager.tier,
                        "usage_percent": self.tier_manager.get_usage_percent(),
                    }

            # -------------------------
            # Context
            # -------------------------
            previous_posts = await self.db.get_recent_posts_formatted(limit=40)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"""
Recent tweets (do not repeat wording or structure):
{previous_posts}

Write one new tweet.
Output ONLY the tweet text.
""",
                },
            ]

            # -------------------------
            # Generate tweet
            # -------------------------
            raw_result = await self.safe_chat(messages)
            post_text = normalize_post_text(raw_result)

            # Ensure non-empty string
            post_text = (post_text or "").strip()
            if not post_text:
                post_text = random.choice(FALLBACK_TWEETS)
                logger.warning("[AUTOPOST] LLM returned empty, using fallback tweet.")

            # Clamp length
            post_text = post_text[:MAX_CHARS].rstrip()

            # -------------------------
            # Post to Twitter
            # -------------------------
            tweet_data = await self.twitter.post(post_text)
            if not tweet_data or "id" not in tweet_data:
                raise RuntimeError("Twitter post returned invalid response")

            # -------------------------
            # Save to DB
            # -------------------------
            await self.db.save_post(
                post_text,
                tweet_data["id"],
                include_picture=False,
            )

            duration = round(time.time() - start_time, 1)
            logger.info(f"[AUTOPOST] Posted successfully in {duration}s")

            return {
                "success": True,
                "tweet_id": tweet_data["id"],
                "text": post_text,
                "duration_seconds": duration,
            }

        except Exception as e:
            duration = round(time.time() - start_time, 1)
            logger.error(f"[AUTOPOST] FAILED: {e}")
            logger.exception(e)
            return {
                "success": False,
                "error": str(e),
                "duration_seconds": duration,
            }
