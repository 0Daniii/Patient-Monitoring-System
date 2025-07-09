# backend/Dockerfile
FROM python:3.10-slim

WORKDIR /app

# install runtime deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# bring in your code
COPY . .

# expose Flask port
EXPOSE 8080

# entrypoint uses FLASK_APP & FLASK_ENV from compose
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
