FROM node:22-alpine AS build
WORKDIR /src
COPY package*.json ./
RUN npm install --no-audit --no-fund
COPY . ./
RUN npm run build
FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN mkdir -p /var/cache/nginx /var/run /var/log/nginx && chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx /usr/share/nginx/html
USER nginx
EXPOSE 8080
