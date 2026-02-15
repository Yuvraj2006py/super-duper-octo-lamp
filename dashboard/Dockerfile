FROM node:20-alpine

WORKDIR /workspace/dashboard

COPY dashboard/package.json ./
RUN npm install

COPY dashboard .

EXPOSE 3000
CMD ["npm", "run", "dev"]
