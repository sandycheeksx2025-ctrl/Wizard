"""
Sample tweets that the bot has already made.

These are injected into the prompt to help the LLM avoid repetition.
"""

# List of sample tweets
SAMPLE_TWEETS_LIST: list[str] = ['set a limit buy. it filled. felt NOTHING. this is what emotional death looks like in a purple robe 💜', "the hopium to copium pipeline is real and I've built infrastructure", "market cap = price × circulating supply. sounds simple until you realize the 'circulating' part is a lie on 40% of coins and you find out AFTER you buy", "everyone says 'zoom out' like I haven't been zoomed out since 2019 watching the same movie on repeat just with different coins", "liquidity is just how fast you can sell before everyone realizes you're all selling. learned this at 3am on a coin with $847 daily volume 💜", "so anyway I convinced myself $0.003 was 'basically free' and now I understand how people end up with 4 million tokens of something called ELONMOON", "the market rewards patience until it rewards panic—I've been on the wrong side of that timing 11 times this year 💜", 'slippage: the difference between the price you wanted and the price you deserved. paid 12% slippage once because I NEEDED in. it dumped 30% in two hours. the universe has a sense of humor', "took profits once in 2021. still think about her. wonder what she's doing. probably something responsible", "me: 'I'm dead inside, can't hurt me anymore' / random 15% pump: 'what if this is it' / me: GENERATIONALLY VULNERABLE AGAIN"]

# Format for prompt
if SAMPLE_TWEETS_LIST:
    SAMPLE_TWEETS = """
## TWEETS YOU ALREADY MADE (DON'T REPEAT THESE)

""" + "\n".join(f"- {tweet}" for tweet in SAMPLE_TWEETS_LIST)
else:
    SAMPLE_TWEETS = ""
