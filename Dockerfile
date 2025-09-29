FROM python:3.11-slim

# ncurses para TUI y locales UTF-8 para caracteres de caja
RUN apt-get update && apt-get install -y --no-install-recommends \
    libncursesw6 ncurses-term locales \
 && rm -rf /var/lib/apt/lists/* \
 && localedef -i C -c -f UTF-8 C.UTF-8 || true


ENV PYTHONUNBUFFERED=1 LANG=C.UTF-8 TERM=xterm

WORKDIR /app

# (si tienes requirements.txt, descomenta estas dos líneas)
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código
COPY src/ /app/src/

# Comando por defecto
CMD ["python", "-m", "src.main"]
