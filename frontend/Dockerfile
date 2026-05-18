FROM node:20-alpine AS base

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

FROM base AS dev

EXPOSE 3000

ENV NODE_ENV=development
CMD ["npm", "run", "dev"]

FROM base AS builder

RUN npm run build

FROM node:20-alpine AS production

WORKDIR /app

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

ENV NODE_ENV=production
CMD ["node", "server.js"]
