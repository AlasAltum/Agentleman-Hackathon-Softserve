FROM node:20-bookworm-slim

WORKDIR /app

ENV CI=1

RUN corepack enable

COPY package.json yarn.lock .yarnrc.yml ./

RUN yarn install --immutable

COPY . .

RUN chmod +x ./scripts/*.sh

EXPOSE 9000

CMD ["sh", "-c", "yarn build && mkdir -p /app/public && cp -r /app/.medusa/server/public/admin /app/public/admin && yarn start"]