# Contexto de build: raíz del repo (para copiar libs/comun y contracts/)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/ruteo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY libs/comun ./comun
COPY contracts ./contracts
COPY services/ruteo/app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
