import praw
import random
import os
import redis
import time
import uuid
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, request
from flask_cors import CORS, cross_origin
from flask_socketio import SocketIO, emit, join_room, leave_room

load_dotenv()

app = Flask(__name__, static_folder='./ui', static_url_path='/')
socketio = SocketIO(app, host="0.0.0.0", cors_allowed_origins="*")

redis_cache = redis.from_url(os.environ['REDIS_URL'], charset="utf-8", decode_responses=True)

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

    KEYS = {}

    def __init__(self, uuid):
        self.id = uuid
        for key in self.KEYS:
            one_or_many, constr = self.KEYS[key]
            self.createFuncPair(key, one_or_many, constr)

    def createFuncPair(self, key, one_or_many, constr):
        redis_key = '%s:%s' % (self.id, key)

        def setFunc(value):
            if one_or_many == RedisObject.ONE:
                redis_cache.set(redis_key, value)
            else:
                redis_cache.sadd(redis_key, value)
        
        def getFunc():
            if one_or_many == RedisObject.ONE:
                result = redis_cache.get(redis_key)
                return constr(
                    result
                ) if result else None
            else:
                return [
                    constr(value) for value in list(redis_cache.smembers(redis_key) or [])
                ]

        def deleteFunc(value):
            if one_or_many == RedisObject.ONE:
                redis_cache.delete(redis_key)
            else:
                redis_cache.srem(redis_key, value)

        setattr(self, '_get_%s' % key, getFunc)
        setattr(self, '_%s_%s' % ('set' if one_or_many == RedisObject.ONE else 'add_to', key), setFunc)
        setattr(self, '_%s_%s' % ('remove' if one_or_many == RedisObject.ONE else 'remove_from', key), setFunc)

class Player(RedisObject):
    KEYS = {
        'name': (RedisObject.ONE, str),
        'answer_id': (RedisObject.ONE, str),
        'score': (RedisObject.ONE, int)
    }

    def addPoint(self):
        score = self._get_score() or 0
        score += 1
        self._set_score(score)

class Answer(RedisObject):
    KEYS = {
        'player_id': (RedisObject.ONE, str),
        'content': (RedisObject.ONE, str)
    }
    
    def selectAsWinner(self):
        p = Player(self._get_player_id())
        p.addPoint()

class Game(RedisObject):
    DRAW_DURATION = 60
    VOTE_DURATION = 30
    STATE_WAIT = 0
    STATE_DRAW = 1
    STATE_VOTE = 2

    KEYS = {
        'artist': (RedisObject.ONE, str),
        'players': (RedisObject.MANY, str),
        'post': (RedisObject.ONE, str),
        'state': (RedisObject.ONE, int),
        'answers': (RedisObject.MANY, str)
    }

    def newRound(self):
        #get random artist
        artist_candidates = [
            player for player in self._get_players() if player != self._get_artist()
        ]
        self._set_artist(artist_candidates[random.randint(0, len(artist_candidates) - 1)])
        emit('new_artist', self._get_artist(), room=self.id)
        
        #get random post
        random_post = posts[random.randint(0, len(posts) - 1)].title
        self._set_post(random_post)
        emit('new_post', random_post, room=self._get_artist())

        self._set_state(Game.STATE_WAIT)
        emit('state_change', Game.STATE_WAIT, room=self.id)

    def getAnswerMap(self):
        answers = [Answer(a_id) for a_id in self._get_answers()]
        return {answer.id : answer._get_content() for answer in answers}

    def getPlayerMap(self):
        players = [Player(p_id) for p_id in self._get_players()]
        return {player.id : player._get_name() for player in players}

def start_game(game_id):
    g = Game(game_id)

    g._set_state(Game.STATE_DRAW)
    emit('state_change', Game.STATE_DRAW, room=game_id)
    socketio.sleep(Game.DRAW_DURATION)

    g._set_state(Game.STATE_VOTE)
    emit('state_change', Game.STATE_VOTE, room=game_id)
    emit('answers_in', g.getAnswerMap(), room=game_id)
    socketio.sleep(Game.VOTE_DURATION)
    7
    g.newRound()

@socketio.on('join')
def join_game(data):
    game_id = data['game_id']
    name = data['name']
    join_room(game_id)
    join_room(request.sid)
    g = Game(game_id)
    p = Player(request.sid)
    p._set_name(name)
    if not g._get_players():
        g._add_to_players(request.sid)
        g.newRound()
    else:
        g._add_to_players(request.sid)
    emit('players_update', g.getPlayerMap(), room=game_id)

@socketio.on('draw')
def handle_draw(data):
    g = Game(data['game_id'])
    if (request.sid == g._get_artist()):
        if (not g._get_state()):
            start_game(data['game_id'])
        elif (g._get_state() == Game.STATE_DRAW):
            emit('draw', data['points'], room=data['game_id'])

@socketio.on('answer')
def handle_answer(data):
    g = Game(data['game_id'])
    p = Player(request.sid)
    if (request.sid != g._get_artist() and g._get_state() == Game.STATE_DRAW and not p._get_answer_id()):
        ans_uuid = uuid.uuid4().hex
        p._set_answer_id(ans_uuid)
        a = Answer(ans_uuid)
        a._set_player_id(request.sid)
        a._set_content(data['content'])
        g._add_to_answers(ans_uuid)

@socketio.on('vote')
def handle_vote(data):
    g = Game(data['game_id'])
    if (request.sid == g._get_artist() and g._get_state() == Game.STATE_VOTE):
        a = Answer(data['answer_id'])
        a.selectAsWinner()

@app.route('/')
@cross_origin()
def index():
    return redirect('/%s' % uuid.uuid4().hex)

@app.route('/<game_id>')
@cross_origin()
def game_room(game_id):
    return app.send_static_file('index.html')

if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=(os.environ['PORT'] if 'PORT' in os.environ else 5000), message_queue=os.environ['REDIS_URL'])
