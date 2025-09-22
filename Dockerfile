# Usamos una imagen base de Python oficial
FROM python:3.9-slim

# Instalar dependencias de sistema necesarias
RUN apt-get update && apt-get install -y \
    build-essential \
    net-tools \
    iproute2 \
    python3-dev \
    libpcap-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear y establecer el directorio de trabajo
WORKDIR /app

# Copiar el código fuente al contenedor
COPY . .

# Instalar las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Configuración de la entrada por defecto
CMD ["python3", "scripts/run.py"]
