# Placeholder: serves static files with nginx.
# Once the React + Vite app exists, switch to a two-stage build:
#   FROM node:20-alpine AS build  ->  npm ci && npm run build
#   FROM nginx:alpine             ->  COPY --from=build /app/dist /usr/share/nginx/html
FROM nginx:1.27-alpine
COPY public /usr/share/nginx/html
EXPOSE 80
