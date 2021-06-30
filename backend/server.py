import praw
import random
import os
from dotenv import load_dotenv
from flask import Flask

load_dotenv()

def get_praw_kwargs():
    praw_key_tups = [('REDDIT_CLIENT_ID', 'client_id'), ('REDDIT_CLIENT_SECRET', 'client_secret'), ('REDDIT_PASSWORD', 'password')]
    return {
        praw_key: os.environ[env_key] for (env_key, praw_key) in praw_key_tups
    }

reddit = praw.Reddit(
    **get_praw_kwargs(),
    user_agent='tifu.io',
    username='rylo-kin'
)

tifu = reddit.subreddit('tifu')

posts = [submission for submission in tifu.top('week')]

class Game():
    def __init__(self, host):
        self.artist = None
        self.players = []
        self.post = posts[random.randint(0, len(posts))]