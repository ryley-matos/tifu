import eventlet
eventlet.monkey_patch()

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
socketio = SocketIO(app, host="0.0.0.0", cors_allowed_origins="*", message_queue=os.environ['REDIS_URL'], async_mode='eventlet')

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
        setattr(self, '_%s_%s' % ('remove' if one_or_many == RedisObject.ONE else 'remove_from', key), deleteFunc)

class Player(RedisObject):
    KEYS = {
        'name': (RedisObject.ONE, str),
        'answer_id': (RedisObject.ONE, str),
    }

class Answer(RedisObject):
    IMAGE_DATA = 0
    PHRASE = 1

    KEYS = {
        'player_id': (RedisObject.ONE, str),
        'content': (RedisObject.ONE, str),
        'image_or_phrase': (RedisObject.ONE, int)
    }

class Game(RedisObject):
    DRAW_DURATION = 45
    WRITE_DURATION = 30
    STATE_DRAW = 0
    STATE_WRITE = 1
    STATE_VIEW = 2

    KEYS = {
        'current_player': (RedisObject.ONE, str),
        'players': (RedisObject.MANY, str),
        'post': (RedisObject.ONE, str),
        'state': (RedisObject.ONE, int),
        'answers': (RedisObject.MANY, str),
        'admin': (RedisObject.ONE, str)
    }

    def getPlayerMap(self):
        players = [Player(p_id) for p_id in self._get_players()]
        return {player.id : player._get_name() for player in players}

    def getAnswerMap(self):
        answers = [Answer(a_id) for a_id in self._get_answers()]
        return {answer.id: answer._get_player_id() for answer in answers}

    def nextStep(self):
        answerMap = self.getAnswerMap()
        players = self._get_players()
        uneligiblePlayers = [answerMap[key] for key in answerMap]
        eligblePlayers = [player for player in players if player not in uneligiblePlayers]
        if not eligblePlayers:
            return False
        state = self._get_state()
        self._set_current_player(eligblePlayers[random.randint(0, len(eligblePlayers) - 1)])
        self._set_state(self.STATE_DRAW if state == self.STATE_WRITE else self.STATE_WRITE)
        return True
        
    def newRound(self):
        answers = self._get_answers()
        for answer in answers:
            self._remove_from_answers(answer)

        random_post = posts[random.randint(0, len(posts) - 1)].title
        players = self._get_players()

        self._set_current_player(players[random.randint(0, len(players) - 1)])
        self._set_post(random_post)
        self._set_state(self.STATE_DRAW)

@socketio.on('answer')
def handle_answer(data):
    game_id = data['game_id']
    g = Game(game_id)
    if (request.sid == g._get_current_player()): #user allowed to answer
        a_uuid = uuid.uuid4().hex
        a = Answer(a_uuid)
        a._set_image_or_phrase(g._get_state())
        a._set_player_id(request.sid)
        a._set_content(data['content'])
        g._add_to_answers(a_uuid)
        if (not g.nextStep()):
            emit('game_end', room=game_id)
        else:
            player_id = g._get_current_player()
            payload = {
                'state': g._get_state(),
                'answer': a._get_content()
            }
            emit('next_player', player_id, room=game_id)
            emit('next_step', payload, room=player_id)

@socketio.on('start_game')
def start_game(data):
    game_id = data['game_id']
    g = Game(game_id)
    if (request.sid == g._get_admin()):
        g.newRound()
        payload = {
            'state': g._get_state(),
            'answer': g._get_post()
        }
        player_id = g._get_current_player()
        emit('next_player', player_id, room=game_id)
        emit('next_step', payload, room=player_id)
        emit('game_start', room=game_id)


@socketio.on('join')
def join_game(data):
    game_id = data['game_id']
    name = data['name']
    join_room(game_id)
    join_room(request.sid)
    g = Game(game_id)
    p = Player(request.sid)
    p._set_name(name)
    g._add_to_players(request.sid)
    if (not g._get_admin()):
        g._set_admin(request.sid)
        emit('admin', room=(request.sid))
    emit('players_update', g.getPlayerMap(), room=game_id)

if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=(os.environ['PORT'] if 'PORT' in os.environ else 5000))
