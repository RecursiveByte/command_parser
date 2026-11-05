FROM python:3.13-slim

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/label.py ./worker/label.py
COPY prompts/teacher_prompt.txt ./prompts/teacher_prompt.txt

ENV PYTHONUNBUFFERED=1

CMD ["python", "worker/label.py"]