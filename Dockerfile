FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static ./static
COPY templates ./templates
COPY env.simple_ui.example ./env.simple_ui.example
COPY README.md ./README.md

ENV SIMPLE_UI_PORT=4040

EXPOSE 4040

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "4040"]
