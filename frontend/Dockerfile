# --- Hot-reload dev (docker compose --profile dev) ---
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS development

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# --- Production static assets + nginx ---
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE=
ARG VITE_ONLYOFFICE_URL=/office-ds
ARG VITE_ONLYOFFICE_DIRECT_PORT=
ARG VITE_ONLYOFFICE_DIRECT_URL=
ARG VITE_CANARY_OPEN_PDF_IN_ONLYOFFICE=
ARG CANARY_PUBLIC_URL=

ENV VITE_API_BASE=$VITE_API_BASE \
    VITE_ONLYOFFICE_URL=$VITE_ONLYOFFICE_URL \
    VITE_ONLYOFFICE_DIRECT_PORT=$VITE_ONLYOFFICE_DIRECT_PORT \
    VITE_ONLYOFFICE_DIRECT_URL=$VITE_ONLYOFFICE_DIRECT_URL \
    VITE_CANARY_OPEN_PDF_IN_ONLYOFFICE=$VITE_CANARY_OPEN_PDF_IN_ONLYOFFICE \
    CANARY_PUBLIC_URL=$CANARY_PUBLIC_URL

RUN npm run build

FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS production

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
