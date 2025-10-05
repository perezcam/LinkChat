FROM python:3.11-slim

# Libs que Pygame/SDL suele necesitar (video+GL+fuentes+audio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libx11-6 libxext6 libxrender1 libxrandr2 libxcursor1 libxinerama1 libxi6 \
    libgl1 libegl1 libasound2 fonts-dejavu \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencias de la UI (pinea versiones)
COPY ./requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglx-mesa0 \
    libgl1-mesa-dri \
    mesa-utils \
    fontconfig \
 && rm -rf /var/lib/apt/lists/*
# Código de la UI (modo prod; en dev lo montamos como volumen)
COPY . /app/

# Pequeño entrypoint que lee IPC_SOCKET y lanza la UI
COPY ./entrypoint.py /app/entrypoint.py

ENV SDL_VIDEODRIVER=x11 \
    PYTHONUNBUFFERED=1

CMD ["python","/app/entrypoint.py"]
