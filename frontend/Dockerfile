# Build React application
FROM node as builder

COPY ./package.json .
RUN npm install

COPY . .
RUN npm run build

# Serve the built static content with Nginx
FROM nginx
EXPOSE 80
COPY ./nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build /usr/share/nginx/html
