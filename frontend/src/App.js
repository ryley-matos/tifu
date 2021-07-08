import './App.css';

import io from 'socket.io-client';

import { useEffect, useState, useRef } from 'react'
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

const Whiteboard = ({game_id, remoteDraw=false}) => {
  const canvasRef = useRef()
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

  useEffect(() => {
    if (remoteDraw) {
      socket.on('draw', (points) => drawLine(points))
    }
    return () => {
      socket.off('draw')
    }
  }, [remoteDraw])



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
          if (!marking || remoteDraw)
            return
          const offset = canvasRef?.current?.getBoundingClientRect()
          const {xn: x0, yn: y0} = normalize(lastX, lastY)
          const {xn: x1, yn: y1} = normalize(e.clientX - offset.left, e.clientY - offset.top)
          socket.emit('draw', {game_id, points: {x0, y0, x1,  y1}})
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
}

const STATE_WAITING = 0
const STATE_DRAWING = 1
const STATE_VOTING = 2

const Game = ({id}) => {
  const [socketId, setSocketId] = useState(null)
  const [artistId, setArtistId] = useState(null)
  const [post, setPost] = useState('')
  const [state, setState] = useState()
  const [alertSeen, setAlertSeen] = useState(false)

  const isArtist = socketId && socketId == artistId

  useEffect(() => {
    if (id) {
      socket.on('new_artist', id => setArtistId(id))
      socket.on('new_post', (post) => setPost(post))
      socket.on('state_change', (state) => setState(state))
      socket.emit('join', {game_id: id, name: 'test_name'})
      return () => {
        socket.off('new_artist')
        socket.off('new_post')
      }
    }
  }, [id])

  useEffect(() => {
    socket.on('connect', () => setSocketId(socket.id))
    return () => {
      socket.off('connect')
    }
  }, [])

  useEffect(() => {
    if (isArtist) {
      setAlertSeen(false)
    }
  }, [isArtist])

  return (
    <Container>
      <Whiteboard game_id={id} remoteDraw={!isArtist}/>
      <Modal isOpen={(isArtist && !alertSeen)}>
      <ModalOverlay/>
        <ModalContent p={12}>
          <Center>
              <Text fontSize="128px">
                🎨
              </Text>
          </Center>
          <Center>
            <Text
              bgGradient="linear(to-l, #000000,#FF0000)"
              bgClip="text"
              fontSize="4xl"
              fontWeight="extrabold"
            >
              you are the artist
            </Text>
          </Center>
          <Center>
            <Button onClick={() => setAlertSeen(true)}>
              start
            </Button>
          </Center>
        </ModalContent>
      </Modal>
      <Text
        bgGradient="linear(to-l, #000000,#FF0000)"
        bgClip="text"
        fontSize="4xl"
        fontWeight="extrabold"
      >
        r/tifu...
      </Text>
      {isArtist ?
        <div>
          <Text>{post.toLowerCase().replace('tifu ', '')}</Text>
        </div>
      :
        <Answer game_id={id}/>
      }
    </Container>
  )
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
