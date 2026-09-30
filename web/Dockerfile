# 多阶段构建：workspace 根构建 → nginx 静态托管 + API 反代
FROM node:22-slim AS build
WORKDIR /repo
COPY package.json ./
COPY packages/core/package.json packages/core/
COPY web/package.json web/
RUN npm install --no-audit --no-fund
COPY packages ./packages
COPY web ./web
RUN npm run build -w web

FROM nginx:alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/web/dist /usr/share/nginx/html
EXPOSE 80
