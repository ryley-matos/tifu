import praw
import random
import os
import logging
import redis
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, request
from flask_cors import CORS, cross_origin
from flask_socketio import SocketIO, emit, join_room, leave_room

logger = logging.getLogger('Game Server')

load_dotenv()

app = Flask(__name__, static_folder='../frontend/build', static_url_path='/')
socketio = SocketIO(app, host="0.0.0.0", cors_allowed_origins="*")

redis_cache = redis.from_url(os.environ['REDIS_URL'])

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

class RedisObject():
    ONE = 0
    MANY = 1

    def __init__(self, uuid):
        self.id = uuid

    def getDict(self):
        result = dict()
        for (k, k_type) in self.KEYS:
            if k_type == RedisObject.ONE:
                result[k] = redis_cache.get('%s:%s' % (self.id, k))
            else:
                result[k] = redis_cache.smembers('%s:%s' % (self.id, k))
        return result


class Game(RedisObject):

    KEYS = [('artist', RedisObject.ONE), ('players', RedisObject.MANY), ('post', RedisObject.ONE)]
    
    def setArtist(self, player_id):
        emit('set_artist', player_id, room=self.id)
        redis_cache.set('%s:%s' % (self.id, 'artist'), player_id)

    def getArtist(self):
        return redis_cache.get('%s:%s' % (self.id, 'artist'))

    def addPlayer(self, player_id):
        emit('add_player', player_id, room=self.id)
        redis_cache.sadd('%s:%s' % (self.id, 'players'), player_id)

    def removePlayer(self, player_id):
        emit('remove_player', player_id, room=self.id)
        redis_cache.srem('%s:%s' % (self.id, 'players'), player_id)

    def getPlayers(self):
        return redis_cache.smembers('%s:%s' % (self.id, 'players'))

    def newPost(self):
        new_post = posts[random.randint(0, len(posts))].title
        emit('new_post', new_post, room=self.id)
        redis_cache.set('%s:%s' % (self.id, 'post'), new_post)

    def getPost(self):
        return redis_cache.get('%s:%s' % (self.id, 'post'))



@app.route('/<room_id>')
@cross_origin()
def index(room_id):
    return app.send_static_file('index.html')

@socketio.on('join')
def join_game(room_id):
    join_room(room_id)
    g = Game(room_id)
    artist = g.getArtist()
    if not artist:
        g.setArtist(request.sid)
        g.newPost()
    g.addPlayer(request.sid)
    print(g.getDict())

if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=(os.environ['PORT'] if 'PORT' in os.environ else 5000))

