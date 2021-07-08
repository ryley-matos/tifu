cd frontend && yarn build && cd .. && cp -R ./frontend/build ./backend/ui && docker-compose build && docker-compose up
