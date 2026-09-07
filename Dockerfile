FROM mcr.microsoft.com/playwright:v1.63.0-noble

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY playwright.config.ts README.md ./
COPY tests ./tests

ENV CI=true
ENV HEADLESS=true

CMD ["npm", "test", "--", "--workers=1"]
