# Imagen base
FROM python:3.11-slim


# Paquetes mínimos de red para diagnóstico (opcionales pero útiles)
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 iputils-ping net-tools ethtool tcpdump \
  && rm -rf /var/lib/apt/lists/*

# Evita buffering en logs
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Copiamos el proyecto (ajusta si usas un subdirectorio)
COPY . /app

# Instala requirements si existe
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Variables que tu app puede leer (INTERFACE, ALIAS, ETHER_TYPE)
ENV INTERFACE=eth0 \
    ALIAS=Nodo-Docker \
    ETHER_TYPE=0x88B5

# Comando por defecto (tu main ya coordina socket -> threads -> discovery)
ENV PYTHONPATH=/app
CMD ["python", "-u", "-m", "src.main"]
