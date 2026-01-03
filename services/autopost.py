"""
Merged Purrple autoposting for your other bot.

Replaces legacy autopost flow with:
- Agent-based planning
- Step-by-step tool execution
- Cleaned narrative posts (no catchphrases, no 💜)
- Fallback tweets if LLM fails
"""

import json
import logging
import time
import random
from typing import Any

from services.database import Database
from services.llm import LLMClient
from services.twitter import TwitterClient
from tools.registry import TOOLS, get_tools_description
from config.prompts.agent_autopost import AUTOPOST_AGENT_PROMPT
from config.personality import INSTRUCTIONS

logger = logging.getLogger(__name__)

# Sample tweets (avoid repetition)
SAMPLE_TWEETS_LIST = [
    'set a limit buy. it filled. felt NOTHING. this is what emotional death looks like in a robe',
    "the hopium to copium pipeline is real and I've built infrastructure",
    "market cap = price × circulating supply. sounds simple until you realize the 'circulating' part is a lie on 40% of coins and you find out AFTER you buy",
    "everyone says 'zoom out' like I haven't been zoomed out since 2019 watching the same movie on repeat just with different coins",
    "liquidity is just how fast you can sell before everyone realizes you're all selling. learned this at 3am on a coin with $847 daily volume",
    "I convinced myself $0.003 was 'basically free' and now I understand how people end up with 4 million tokens of something called ELONMOON",
    "the market rewards patience until it rewards panic—I've been on the wrong side of that timing 11 times this year",
    'slippage: the difference between the price you wanted and the price you deserved. paid 12% slippage once because I NEEDED in. it dumped 30% in two hours. the universe has a sense of humor',
    "took profits once in 2021. still think about her. wonder what she's doing. probably something responsible",
    "me: 'I'm dead inside, can't hurt me anymore' / random 15% pump: 'what if this is it' / me: GENERATIONALLY VULNERABLE AGAIN"
]

SAMPLE_TWEETS = "\n".join(f"- {tweet}" for tweet in SAMPLE_TWEETS_LIST) if SAMPLE_TWEETS_LIST else ""

# Fallback tweets (different narrative)
FALLBACK_TWEETS = [
    "traced the dust on my keyboard made a pattern only I could read—markets are whispering secrets I still don't understand",
    "quietly watched my screen glow all night graphs like rivers I can't swim, yet I keep diving anyway",
    "remembered rug pull #7 laughed at the chaos, cried at the learning, typed another limit order anyway",
    "press paws on the charts saw patterns in candlesticks, thought I cracked the code—then sold too early",
    "staring at empty charts imagining profits that will never come, still writing notes for version #∞"
]

def get_agent_system_prompt() -> str:
    tools_desc = get_tools_description()
    return AUTOPOST_AGENT_PROMPT.format(tools_desc=tools_desc)

SYSTEM_PROMPT = f"""
You are the bot persona. Follow these instructions carefully when generating posts:

{INSTRUCTIONS}
"""

class AutoPostService:
    """Merged Purrple autopost service."""

    def __init__(self, db: Database, tier_manager=None):
        self.db = db
        self.llm = LLMClient()
        self.twitter = TwitterClient()
        self.tier_manager = tier_manager

    async def run(self) -> dict[str, Any]:
        start_time = time.time()
        logger.info("[AUTOPOST] === Starting ===")

        try:
            # Tier check
            if self.tier_manager:
                can_post, reason = self.tier_manager.can_post()
                if not can_post:
                    logger.warning(f"[AUTOPOST] Blocked: {reason}")
                    return {
                        "success": False,
                        "error": f"posting_blocked: {reason}",
                        "tier": self.tier_manager.tier,
                        "usage_percent": self.tier_manager.get_usage_percent()
                    }

            # Previous posts
            previous_posts = await self.db.get_recent_posts_formatted(limit=50)

            # Initial messages
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT + get_agent_system_prompt()},
                {"role": "user", "content": f"""Create a Twitter post. Here are your previous posts (don't repeat):

{SAMPLE_TWEETS}

Now create your plan. What tools do you need (if any)?"""}
            ]

            # Get plan
            plan_result = await self.llm.chat(messages, {"type": "plan"})
            plan = plan_result.get("plan", [])
            reasoning = plan_result.get("reasoning", "")
            messages.append({"role": "assistant", "content": json.dumps(plan_result)})

            image_bytes = None
            tools_used = []

            # Execute plan
            for i, step in enumerate(plan):
                tool_name = step.get("tool")
                params = step.get("params", {})
                tools_used.append(tool_name)

                if tool_name in TOOLS:
                    result = await TOOLS[tool_name](**params)
                    messages.append({"role": "user", "content": f"Tool result ({tool_name}): {result}"})

                reaction = await self.llm.chat(messages, {"type": "tool_reaction"})
                messages.append({"role": "assistant", "content": reaction.get("thinking", "")})

                if tool_name == "generate_image":
                    image_bytes = result

            # Final tweet
            messages.append({"role": "user", "content": "Now write your final tweet text. Just the tweet, nothing else."})
            post_result = await self.llm.chat(messages, {"type": "post_text"})
            post_text = post_result.get("post_text", "").strip()

            if not post_text:
                post_text = random.choice(FALLBACK_TWEETS)

            # Upload image
            media_ids = None
            if image_bytes:
                try:
                    media_id = await self.twitter.upload_media(image_bytes)
                    media_ids = [media_id]
                except Exception as e:
                    logger.error(f"[AUTOPOST] Image upload failed: {e}")

            # Post to Twitter
            tweet_data = await self.twitter.post(post_text, media_ids=media_ids)

            # Save to database
            await self.db.save_post(post_text, tweet_data["id"], include_picture=bool(image_bytes))

            duration = round(time.time() - start_time, 1)
            return {
                "success": True,
                "tweet_id": tweet_data["id"],
                "text": post_text,
                "plan": plan,
                "reasoning": reasoning,
                "tools_used": tools_used,
                "has_image": bool(image_bytes),
                "duration_seconds": duration
            }

        except Exception as e:
            duration = round(time.time() - start_time, 1)
            logger.error(f"[AUTOPOST] FAILED: {e}")
            logger.exception(e)
            return {
                "success": False,
                "error": str(e),
                "duration_seconds": duration
            }
