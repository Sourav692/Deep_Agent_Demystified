# Build context: 07_Deep_Agents/ (one level above app/)
# Run: docker build -f app/Dockerfile -t deep-agent .

FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci
COPY app/frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

# Install backend dependencies
COPY app/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY app/backend/ ./backend/

# Copy skills from parent directory (now reachable from context)
COPY skills/ ./skills/

# Copy built frontend into backend's expected path
COPY --from=frontend-build /frontend/build ./frontend/build/

# Expose port
EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
