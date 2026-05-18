FROM python:3.14-slim

WORKDIR /app
COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["python", "app.py"]
