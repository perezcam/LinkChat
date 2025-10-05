FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libncursesw6 ncurses-term locales \
 && rm -rf /var/lib/apt/lists/* \
 && localedef -i C -c -f UTF-8 C.UTF-8 || true


ENV PYTHONUNBUFFERED=1 LANG=C.UTF-8 TERM=xterm

WORKDIR /app


COPY src/ /app/src/


CMD ["python", "-m", "src.app_server"]
