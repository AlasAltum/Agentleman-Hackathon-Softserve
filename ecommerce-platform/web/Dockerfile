FROM node:20-bookworm-slim

WORKDIR /app

ENV CI=1

RUN corepack enable

COPY package.json yarn.lock .yarnrc.yml ./
COPY .yarn/ .yarn/

RUN yarn install --immutable

COPY . .

RUN chmod +x ./scripts/*.sh

EXPOSE 8001

CMD ["./scripts/start.sh"]