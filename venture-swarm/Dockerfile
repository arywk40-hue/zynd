FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
RUN chmod +x /app/scripts/start_hf_space.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 7860

CMD ["sh", "scripts/start_hf_space.sh"]
