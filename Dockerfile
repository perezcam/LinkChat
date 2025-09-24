# Usamos una imagen base de Python oficial
FROM python:3.14-rc-alpine

# Instalar dependencias de sistema necesarias para raw sockets y herramientas de red
RUN apt-get update && apt-get install -y \
    build-essential \
    net-tools \
    iproute2 \
    python3-dev \
    libpcap-dev \
    iputils-ping \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear y establecer el directorio de trabajo
WORKDIR /app

# Copiar el código fuente del proyecto al contenedor
COPY . .

# Instalar las dependencias de Python desde el archivo requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/prepare/network_config.py /network_config.py
RUN chmod +x /network_config.py

# Establecer el script de configuración como el punto de entrada
ENTRYPOINT ["python3", "/network_config.py"]

# Configuración de la entrada por defecto para ejecutar la aplicación después de la configuración de red
CMD ["python3", "src/main.py"]

