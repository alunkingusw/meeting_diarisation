# frontend/Dockerfile

FROM node:18

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "5000"]