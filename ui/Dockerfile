FROM python:3.11-slim
 
 RUN apt-get update && apt-get install -y --no-install-recommends \
     libgl1 \
     libglx-mesa0 \
     libgl1-mesa-dri \
     mesa-utils \
     fontconfig \
  && rm -rf /var/lib/apt/lists/*

  WORKDIR /app

# Dependencias de la UI
COPY ./requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

COPY ./entrypoint.py /app/entrypoint.py

ENV SDL_VIDEODRIVER=x11 \
    PYTHONUNBUFFERED=1

CMD ["python","/app/entrypoint.py"]
