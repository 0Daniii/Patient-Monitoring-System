# keycloak-setup/Dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY setup-keycloak.py .

RUN pip install requests

CMD ["python", "setup-keycloak.py"]