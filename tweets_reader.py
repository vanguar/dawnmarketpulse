import snscrape.modules.twitter as sntwitter

def get_latest_tweets(usernames, max_per_user=1):
    results = []
    for username in usernames:
        try:
            tweets = list(sntwitter.TwitterUserScraper(username).get_items())
            for tweet in tweets[:max_per_user]:
                results.append(f"🗣 @{username}: {tweet.content.strip()}")
        except Exception as e:
            results.append(f"❗Ошибка чтения @{username}: {e}")
    return "\n\n".join(results)

def get_tweet_digest():
    influencers = [
        "elonmusk", "sama", "BillGates", "JeffBezos", "BlackRock", "naval",
        "balajis", "APompliano", "CathieDWood", "RayDalio"
    ]
    tweets_block = get_latest_tweets(influencers, max_per_user=1)
    return f"""Твиты дня 🐦
{tweets_block}

→ Вывод GPT по твитам: что это может означать для рынков?
"""
