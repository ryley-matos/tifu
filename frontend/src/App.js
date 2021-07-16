import './App.css';

import io from 'socket.io-client';

import { useEffect, useState, useRef } from 'react'
import React from 'react'
import { useHistory, useLocation } from 'react-router-dom';

import { Container, Text, Input, Modal, ModalContent, ModalOverlay, Center, Button } from "@chakra-ui/react"
 
const socket = io(process.env.REACT_APP_API_ADDR, {transports: ['websocket']});

const DEF_XY = {lastX: 0, lastY: 0}

const Answer = ({game_id}) => {
  const [content, setContent] = useState('')

  const submit = () => {
    socket.emit('answer', {game_id, content})
  }

  return (
    <div>
      <Input value={content} onChange={e => setContent(e.target.value)}/>
      <button onClick={submit}>submit</button>
    </div>
  )
}

const Whiteboard = React.forwardRef((props, canvasRef) => {
  const [marking, setMarking] = useState(false)
  const [{lastX, lastY}, setLastMark] = useState(DEF_XY)
  const [{width, height}, setDimensions] = useState({width: 500, height: 500})

  const normalize = (x, y) => {
    return {xn: x / width, yn: y / height}
  }

  const startMarking = (e) => {
    const offset = canvasRef?.current?.getBoundingClientRect()
    setLastMark({lastX: e.clientX  - offset.left, lastY: e.clientY - offset.top})
    setMarking(true)
  }

  const endMarking = (e) => {
    setLastMark(DEF_XY)
    setMarking(false)
  }


  const drawLine = ({x0, y0, x1, y1}) => {
    const ctx = canvasRef?.current?.getContext('2d')
    ctx.strokeStyle = '#000000';
    ctx.beginPath()
    ctx.moveTo(x0 * width, y0 * height)
    ctx.lineWidth = 4
    ctx.lineCap = 'round'
    ctx.lineTo(x1 * width, y1 * height)
    ctx.stroke();
  }

  return (
    <div>
      <canvas 
        style={{border: 'solid 2px black'}}
        ref={canvasRef}
        width="500px"
        height="500px"
        onMouseDown={startMarking}
        onMouseUp={endMarking}
        onMouseMove={(e) => {
          if (!marking)
            return
          const offset = canvasRef?.current?.getBoundingClientRect()
          const {xn: x0, yn: y0} = normalize(lastX, lastY)
          const {xn: x1, yn: y1} = normalize(e.clientX - offset.left, e.clientY - offset.top)
          drawLine({x0, y0, x1,  y1})
          setLastMark({
            lastX: e.clientX - offset.left,
            lastY: e.clientY - offset.top
          })
        }}
        onMouseLeave={endMarking}
      />
    </div>
  )
})

const STATE_DRAW = 0
const STATE_WRITE = 1

const PlayerList = ({map}) => {
  return (
    <div>
      {Object.entries(map).map(([key, value]) => <div>{value}</div>)}
    </div>
  )
}

const Game = ({id}) => {
  const [socketId, setSocketId] = useState(null)
  const [currentPlayerId, setCurrentPlayerId] = useState(null)
  const [answer, setAnswer] = useState('')
  const [state, setState] = useState()
  const [admin, setAdmin] = useState(false)
  const [playerMap, setPlayerMap] = useState({})
  const [gameStarted, setGameStarted] = useState(false)
  const [phrase, setPhrase] = useState('')
  const canvasRef = useRef()

  useEffect(() => {
    if (id) {
      socket.on('next_player', nextPlayerId => setCurrentPlayerId(nextPlayerId))
      socket.on('next_step', ({answer, state}) => {
        setAnswer(answer)
        setState(state)
      })
      socket.on('admin', () => setAdmin(true))
      socket.on('players_update', playerMap => setPlayerMap(playerMap))
      socket.on('game_start', () => setGameStarted(true))
      socket.on('game_end', () => setGameStarted(false))
      socket.emit('join', {game_id: id, name: 'test_name'})
      return () => {
        socket.off('next_player')
        socket.off('next_step')
        socket.off('admin')
        socket.off('players_update')
      }
    }
  }, [id])

  useEffect(() => {
    socket.on('connect', () => setSocketId(socket.id))
    return () => {
      socket.off('connect')
    }
  }, [])

  if (admin && !gameStarted) {
    return (
      <div>
        <PlayerList map={playerMap}/>
        <button onClick={() => socket.emit('start_game', {game_id: id})}>
          Start Game
        </button>
      </div>
    )
  }

  if (!gameStarted) {
    return <div>Waiting for game to start...</div>
  }

  if (socketId != currentPlayerId) {
    return <div>Waiting for your turn...</div>
  }

  if (socketId == currentPlayerId) {
    if (state == STATE_DRAW) {
      return (
        <div>
          <Whiteboard ref={canvasRef}/>
          <div>{answer}</div>
          <button onClick={() => socket.emit('answer', {game_id: id, content: canvasRef.current.toDataURL()})}>Submit</button>
        </div>
      )
    }
    else {
      return (
        <div>
          <img src={answer}/>
          <input placeholder="enter your best guess..." onChange={e => setPhrase(e.target.value)}/>
          <button onClick={() => socket.emit('answer', {game_id: id, content: phrase})}>Submit</button>
        </div>
      )
    }
  }



  return null
}

function App() {
  const history = useHistory()
  const location = useLocation()

  useEffect(() => {
    if (location.pathname == '/') {
      history.push(`/${Math.random().toString(36).substring(7)}`)
    }
  }, [location, history])

  const gameId = location.pathname.slice(1)

  return (
    <div className="App">
      <Game id={gameId}/>
    </div>
  );
}

export default App;
