# Stage 1: Build
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

# NEW: Allow Cloud Build to pass the backend URL into the React build
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Stage 2: Serve with Unprivileged Nginx
FROM nginxinc/nginx-unprivileged:alpine

# Copy the updated routing config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the build output
COPY --from=build /app/dist /usr/share/nginx/html

# Expose the non-root port
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]