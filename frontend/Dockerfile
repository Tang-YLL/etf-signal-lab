FROM node:22-alpine AS build
WORKDIR /src
COPY package*.json ./
RUN npm install --no-audit --no-fund
COPY . ./
RUN npm run build
FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# nginx's stock PID file is under /run and not writable by an unprivileged user.
RUN sed -i -E '/^user[[:space:]]+nginx;/d; s@^pid[[:space:]]+[^;]+;@pid /tmp/nginx.pid;@' /etc/nginx/nginx.conf
RUN mkdir -p /var/cache/nginx /var/run /var/log/nginx && chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx /usr/share/nginx/html
USER nginx
EXPOSE 8080
