# frontend/Dockerfile

FROM node:18

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5000

# PORT is supplied by docker-compose (FRONTEND_PORT), defaulting to 5000 for standalone runs.
CMD ["sh", "-c", "npm run dev -- --hostname 0.0.0.0 --port ${PORT:-5000}"]